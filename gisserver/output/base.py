import math
from collections import defaultdict
from typing import List, Set

from django.conf import settings
from django.db import models
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.html import escape

from gisserver import conf
from gisserver.exceptions import InvalidParameterValue
from gisserver.features import FeatureType
from gisserver.geometries import CRS
from gisserver.operations.base import WFSMethod
from gisserver.types import XsdElement

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
    ):
        """Apply presentation layer logic to the queryset."""
        # Avoid fetching relations, fetch these within the same query,
        related = cls._get_prefetch_related(feature_type, output_crs)
        if related:
            queryset = queryset.prefetch_related(*related)

        # Also limit the queryset to the actual fields that are shown.
        # No need to request more data
        fields = [f.orm_field for f in feature_type.xsd_type.elements]
        return queryset.only("pk", *fields)

    @classmethod
    def _get_prefetch_related(
        cls, feature_type: FeatureType, output_crs: CRS
    ) -> List[models.Prefetch]:
        """Summarize which fields read data from relations.

        This combines the input from flattened and complex fields,
        in the unlikely case both variations are used in the same feature.
        """
        fields = defaultdict(set)
        elements = defaultdict(list)

        # Check all elements that render as "dotted" flattened relation
        for xsd_element in feature_type.xsd_type.flattened_elements:
            if xsd_element.source is not None:
                obj_path, field = xsd_element.orm_relation
                elements[obj_path].append(xsd_element)
                fields[obj_path].add(field)

        # Check all elements that render as "nested" complex type:
        for xsd_element in feature_type.xsd_type.complex_elements:
            obj_path = xsd_element.orm_path
            elements[obj_path].append(xsd_element)
            fields[obj_path] = set(f.orm_path for f in xsd_element.type.elements)

        # Since all elements directly reference a relation, these can be prefetched:
        return [
            models.Prefetch(
                obj_path,
                queryset=cls.get_prefetch_queryset(
                    feature_type, elements[obj_path], fields[obj_path], output_crs
                ),
            )
            for obj_path in fields.keys()
        ]

    @classmethod
    def get_prefetch_queryset(
        cls,
        feature_type: FeatureType,
        xsd_elements: List[XsdElement],
        fields: Set[str],
        output_crs: CRS,
    ):
        """Generate a custom queryset that's used to prefetch a reation."""
        return None

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
