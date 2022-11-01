from __future__ import annotations

import math

from django.conf import settings
from django.db import models
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.html import escape

from gisserver import conf
from gisserver.exceptions import InvalidParameterValue
from gisserver.features import FeatureRelation, FeatureType
from gisserver.geometries import CRS
from gisserver.operations.base import WFSMethod

from .results import FeatureCollection


class OutputRenderer:
    """Base class to create streaming responses.

    It receives the collected 'context' data of the WFSMethod.
    """

    #: Allow to override the maximum page size.
    #: This value can be 'math.inf' to support endless pages by default.
    max_page_size = None

    #: Define the content type for rendering the output
    content_type = "application/octet-stream"

    #: An optional content-disposition header to output
    content_disposition = None

    def __init__(
        self,
        method: WFSMethod,
        source_query,
        collection: FeatureCollection,
        output_crs: CRS,
    ):
        """
        Receive the collected data to render.

        :param method: The calling WFS Method (e.g. GetFeature class)
        :param source_query: The query that generated this output.
        :type source_query: gisserver.queries.QueryExpression
        :param collection: The collected data for rendering
        :param output_crs: The requested output projection.
        """
        self.method = method
        self.source_query = source_query
        self.collection = collection
        self.output_crs = output_crs
        self.xml_srs_name = escape(str(self.output_crs))

        # Common elements for output rendering:
        self.server_url = method.view.server_url
        self.app_xml_namespace = method.view.xml_namespace

    @classmethod
    def decorate_collection(
        cls, collection: FeatureCollection, output_crs: CRS, **params
    ):
        """Perform presentation-layer logic enhancements on the queryset."""
        for sub_collection in collection.results:
            # Validate the presentation-level parameters for this feature:
            cls.validate(sub_collection.feature_type, **params)

            queryset = cls.decorate_queryset(
                sub_collection.feature_type,
                sub_collection.queryset,
                output_crs,
                **params,
            )
            if queryset is not None:
                sub_collection.queryset = queryset

    @classmethod
    def validate(cls, feature_type: FeatureType, **params):
        """Validate the presentation parameters"""
        crs = params["srsName"]
        if (
            conf.GISSERVER_SUPPORTED_CRS_ONLY
            and crs is not None
            and crs not in feature_type.supported_crs
        ):
            raise InvalidParameterValue(
                "srsName",
                f"Feature '{feature_type.name}' does not support SRID {crs.srid}.",
            )

    @classmethod
    def decorate_queryset(
        cls,
        feature_type: FeatureType,
        queryset: models.QuerySet,
        output_crs: CRS,
        **params,
    ) -> models.QuerySet:
        """Apply presentation layer logic to the queryset."""
        # Avoid fetching relations, fetch these within the same query,
        related = cls._get_prefetch_related(feature_type, output_crs)
        if related:
            queryset = queryset.prefetch_related(*related)

        # Also limit the queryset to the actual fields that are shown.
        # No need to request more data
        fields = [
            f.orm_field
            for f in feature_type.xsd_type.elements
            if not f.is_many or f.is_array  # exclude M2M, but include ArrayField
        ]
        return queryset.only("pk", *fields)

    @classmethod
    def _get_prefetch_related(
        cls, feature_type: FeatureType, output_crs: CRS
    ) -> list[models.Prefetch]:
        """Summarize which fields read data from relations.

        This combines the input from flattened and complex fields,
        in the unlikely case both variations are used in the same feature.
        """
        return [
            models.Prefetch(
                orm_relation.orm_path,
                queryset=cls.get_prefetch_queryset(
                    feature_type, orm_relation, output_crs
                ),
            )
            for orm_relation in feature_type.orm_relations
        ]

    @classmethod
    def get_prefetch_queryset(
        cls,
        feature_type: FeatureType,
        feature_relation: FeatureRelation,
        output_crs: CRS,
    ) -> models.QuerySet | None:
        """Generate a custom queryset that's used to prefetch a relation."""
        # Multiple elements could be referencing the same model, just take first that is filled in.
        if feature_relation.related_model is None:
            return None

        return feature_type.get_related_queryset(feature_relation)

    def get_response(self):
        """Render the output as streaming response."""
        stream = self.render_stream()
        if isinstance(stream, (str, bytes)):
            # Not a real stream, output anyway as regular HTTP response.
            response = HttpResponse(content=stream, content_type=self.content_type)
        else:
            # A actual generator.
            stream = self._trap_exceptions(stream)
            response = StreamingHttpResponse(
                streaming_content=stream,
                content_type=self.content_type,
            )

        # Add HTTP headers
        for name, value in self.get_headers().items():
            response[name] = value

        # Handover to WSGI server (starts streaming when reading the contents)
        return response

    def get_headers(self):
        """Return the response headers"""
        if self.content_disposition:
            # Offer a common quick content-disposition logic that works for all possible queries.
            sub_collection = self.collection.results[0]
            if sub_collection.stop == math.inf:
                if sub_collection.start:
                    page = f"{sub_collection.start}-end"
                else:
                    page = "all"
            elif sub_collection.stop:
                page = f"{sub_collection.start}-{sub_collection.stop - 1}"
            else:
                page = "results"

            return {
                "Content-Disposition": self.content_disposition.format(
                    typenames="+".join(
                        sub.feature_type.name for sub in self.collection.results
                    ),
                    page=page,
                    date=self.collection.date.strftime("%Y-%m-%d %H.%M.%S%z"),
                    timestamp=self.collection.timestamp,
                )
            }

        return {}

    def _trap_exceptions(self, stream):
        """Decorate the generator to show exceptions"""
        try:
            yield from stream
        except Exception as e:
            # Can't return 500 at this point,
            # but can still tell the client what happened.
            yield self.render_exception(e)
            raise

    def render_exception(self, exception: Exception):
        """Inform the client that the stream processing was interrupted with an exception.
        The exception can be rendered in the format fits with the output.

        Purposefully, not much information is given, so avoid informing clients.
        The actual exception is still raised and logged server-side.
        """
        if settings.DEBUG:
            return f"<!-- {exception.__class__.__name__}: {exception} -->\n"
        else:
            return f"<!-- {exception.__class__.__name__} during rendering! -->\n"

    def render_stream(self):
        """Implement this in subclasses to implement a custom output format."""
        raise NotImplementedError()
