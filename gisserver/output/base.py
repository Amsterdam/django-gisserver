import io

from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.html import escape

from gisserver.operations.base import WFSMethod
from gisserver.types import CRS
from .results import FeatureCollection


class OutputRenderer:
    """Base class to create streaming responses.

    It receives the collected 'context' data of the WFSMethod.
    """

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
    def decorate_collection(cls, collection: FeatureCollection, output_crs, **params):
        """Perform presentation-layer logic enhancements on the queryset."""
        for sub_collection in collection.results:
            queryset = cls.decorate_queryset(
                sub_collection.feature_type,
                sub_collection.queryset,
                output_crs,
                **params
            )
            if queryset is not None:
                sub_collection.queryset = queryset

    @classmethod
    def decorate_queryset(cls, feature_type, queryset, output_crs, **params):
        """Apply presentation layer logic to the queryset."""
        return queryset

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
