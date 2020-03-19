import io

from django.http import StreamingHttpResponse

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
        self, method: WFSMethod, collection: FeatureCollection, output_crs: CRS,
    ):
        """
        Receive the collected data to render.

        :param method: The calling WFS Method (e.g. GetFeature class)
        :param context: The collected data for rendering
        :param params: The input parameters of the request.
        """
        self.method = method
        self.collection = collection
        self.output_crs = output_crs

        # Common elements for output rendering:
        self.xsd_typenames = method.view.KVP["TYPENAMES"]
        self.server_url = method.view.server_url
        self.app_xml_namespace = method.view.xml_namespace

    def get_response(self):
        """Render the output as streaming response."""
        return StreamingHttpResponse(
            self.render_stream(), content_type=self.content_type,
        )

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


class StringBuffer(BaseBuffer):
    """Collect the data as string"""

    buffer_class = io.StringIO
