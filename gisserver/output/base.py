from __future__ import annotations

import logging
import math
import typing

from django.conf import settings
from django.db import models
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.html import escape

from gisserver import conf
from gisserver.exceptions import InvalidParameterValue

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from gisserver.features import FeatureType
    from gisserver.geometries import CRS
    from gisserver.operations.base import WFSMethod
    from gisserver.queries import FeatureProjection, FeatureRelation, QueryExpression

    from .results import FeatureCollection, SimpleFeatureCollection


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
        source_query: QueryExpression,
        collection: FeatureCollection,
        output_crs: CRS,
    ):
        """
        Receive the collected data to render.
        These parameters are received from the ``get_context_data()`` method of the view.

        :param method: The calling WFS Method (e.g. GetFeature class)
        :param source_query: The query that generated this output.
        :param collection: The collected data for rendering.
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
    def decorate_collection(cls, collection: FeatureCollection, output_crs: CRS, **params):
        """Perform presentation-layer logic enhancements on the queryset."""
        for sub_collection in collection.results:
            # Validate the presentation-level parameters for this feature:
            cls.validate(sub_collection.feature_type, **params)

            queryset = cls.decorate_queryset(
                sub_collection.projection,
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
                f"Feature '{feature_type.name}' does not support SRID {crs.srid}.",
                locator="srsName",
            )

    @classmethod
    def decorate_queryset(
        cls,
        projection: FeatureProjection,
        queryset: models.QuerySet,
        output_crs: CRS,
        **params,
    ) -> models.QuerySet:
        """Apply presentation layer logic to the queryset.

        This allows fine-tuning the queryset for any special needs of the output rendering type.

        :param feature_type: The feature that is being queried.
        :param queryset: The constructed queryset so far.
        :param output_crs: The projected output
        :param params: All remaining request parameters (e.g. KVP parameters).
        """
        # Avoid fetching relations, fetch these within the same query,
        prefetches = cls._get_prefetch_related(projection, output_crs)
        if prefetches:
            logger.debug(
                "QuerySet for %s prefetches: %r",
                queryset.model._meta.label,
                [p.prefetch_through for p in prefetches],
            )
            queryset = queryset.prefetch_related(*prefetches)

        logger.debug(
            "QuerySet for %s only retrieves: %r",
            queryset.model._meta.label,
            projection.only_fields,
        )
        return queryset.only("pk", *projection.only_fields)

    @classmethod
    def _get_prefetch_related(
        cls,
        projection: FeatureProjection,
        output_crs: CRS,
    ) -> list[models.Prefetch]:
        """Summarize which fields read data from relations.

        This combines the input from flattened and complex fields,
        in the unlikely case both variations are used in the same feature.
        """
        # When PROPERTYNAME is used, determine all ORM paths (and levels) that this query will touch.
        # The prefetch will only be applied when its field coincide with this list.

        return [
            models.Prefetch(
                orm_relation.orm_path,
                queryset=cls.get_prefetch_queryset(projection, orm_relation, output_crs),
            )
            for orm_relation in projection.orm_relations
        ]

    @classmethod
    def get_prefetch_queryset(
        cls,
        projection: FeatureProjection,
        feature_relation: FeatureRelation,
        output_crs: CRS,
    ) -> models.QuerySet | None:
        """Generate a custom queryset that's used to prefetch a relation."""
        # Multiple elements could be referencing the same model, just take first that is filled in.
        if feature_relation.related_model is None:
            return None

        # This will also apply .only() based on the projection's feature_relation
        return projection.feature_type.get_related_queryset(feature_relation)

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
                page = f"{sub_collection.start}-end" if sub_collection.start else "all"
            elif sub_collection.stop:
                page = f"{sub_collection.start}-{sub_collection.stop - 1}"
            else:
                page = "results"

            return {
                "Content-Disposition": self.content_disposition.format(
                    typenames="+".join(sub.feature_type.name for sub in self.collection.results),
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
            return f"{exception.__class__.__name__}: {exception}"
        else:
            return f"{exception.__class__.__name__} during rendering!"

    def render_stream(self):
        """Implement this in subclasses to implement a custom output format."""
        raise NotImplementedError()

    def get_projection(self, sub_collection: SimpleFeatureCollection) -> FeatureProjection:
        """Provide the projection clause for the given sub-collection."""
        return self.source_query.get_projection(sub_collection.feature_type)
