import io
from collections import defaultdict
from typing import List, Set, Tuple, Type

from django.conf import settings
from django.db import models
from django.db.models import Prefetch
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.html import escape

from gisserver import conf
from gisserver.exceptions import InvalidParameterValue
from gisserver.features import FeatureType
from gisserver.geometries import CRS
from gisserver.operations.base import WFSMethod
from gisserver.types import XsdComplexType, XsdElement

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
        related = [
            # All complex elements directly reference a relation,
            # which can be prefetched directly.
            Prefetch(
                obj_path,
                queryset=cls.get_prefetch_queryset(
                    feature_type, xsd_elements, fields, output_crs
                ),
            )
            for obj_path, xsd_elements, fields in cls._get_prefetch_summary(
                feature_type.xsd_type
            )
        ]

        if related:
            queryset = queryset.prefetch_related(*related)

        # Also limit the queryset to the actual fields that are shown.
        # No need to request more data
        fields = [f.orm_field for f in feature_type.xsd_type.elements]
        return queryset.only("pk", *fields)

    @classmethod
    def _get_prefetch_summary(
        cls, xsd_type: XsdComplexType
    ) -> List[Tuple[str, List[XsdElement], Set[str]]]:
        """Summarize which fields read data from relations.

        This combines the input from flattened and complex fields,
        in the unlikely case both variations are used in the same feature.
        """
        fields = defaultdict(set)
        elements = defaultdict(list)

        for xsd_element in xsd_type.flattened_elements:
            if xsd_element.source is not None:
                obj_path, field = xsd_element.orm_relation
                elements[obj_path].append(xsd_element)
                fields[obj_path].add(field)

        for xsd_element in xsd_type.complex_elements:
            obj_path = xsd_element.orm_path
            elements[obj_path].append(xsd_element)
            fields[obj_path] = set(f.orm_path for f in xsd_element.type.elements)

        return [
            (obj_path, elements[obj_path], fields[obj_path])
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

    @classmethod
    def get_flattened_prefetch_queryset(
        cls, model: Type[models.Model], fields: List[str]
    ):
        """Give the minimum queryset to query the flattened fields."""
        return model.objects.only("pk", *fields)

    def get_response(self):
        """Render the output as streaming response."""
        stream = self.render_stream()
        if isinstance(stream, (str, bytes)):
            return HttpResponse(content=stream, content_type=self.content_type)
        else:
            stream = self._trap_exceptions(stream)
            return StreamingHttpResponse(
                streaming_content=stream, content_type=self.content_type,
            )

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
        """Render the exception in a format that fits with the output."""
        if settings.DEBUG:
            return f"<!-- {exception.__class__.__name__}: {exception} -->\n"
        else:
            return f"<!-- {exception.__class__.__name__} during rendering! -->\n"

    def render_stream(self):
        """Implement this in subclasses to implement a custom output format."""
        raise NotImplementedError()


class BaseBuffer:
    """Fast buffer to write data in chunks.
    This avoids performing too many yields in the output writing.
    Especially for GeoJSON, that slows down the response times.
    """

    buffer_class = None

    def __init__(self, chunk_size=4096):
        self.data = self.buffer_class()
        self.size = 0
        self.chunk_size = chunk_size

    def is_full(self):
        return self.size >= self.chunk_size

    def write(self, value):
        if value is None:
            return
        self.size += len(value)
        self.data.write(value)

    def getvalue(self):
        return self.data.getvalue()

    def clear(self):
        self.data.seek(0)
        self.data.truncate(0)
        self.size = 0


class BytesBuffer(BaseBuffer):
    """Collect the data as bytes."""

    buffer_class = io.BytesIO

    def __bytes__(self):
        return self.getvalue()


class StringBuffer(BaseBuffer):
    """Collect the data as string"""

    buffer_class = io.StringIO

    def __str__(self):
        return self.getvalue()
