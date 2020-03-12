import io
import math

from django.http import StreamingHttpResponse
from django.utils.timezone import now, utc
from gisserver.types import BoundingBox

from gisserver.operations.base import WFSMethod


class OutputRenderer:
    """Base class to create streaming responses.

    It receives the collected 'context' data of the WFSMethod.
    """

    #: Define the content type for rendering the output
    content_type = "application/octet-stream"

    def __init__(self, method: WFSMethod, context: dict, **params):
        """
        Receive the collected data to render.

        :param method: The calling WFS Method (e.g. GetFeature class)
        :param context: The collected data for rendering
        :param params: The input parameters of the request.
        """
        self.method = method
        self.params = params
        self.context = self.get_context_data(**context)

    def get_context_data(self, **context):
        """Allow methods to easily extend the context data"""
        return context

    def get_response(self):
        """Render the output as streaming response."""
        return StreamingHttpResponse(
            self.render_stream(), content_type=self.content_type,
        )

    def render_stream(self):
        """Implement this in subclasses to implement a custom output format."""
        raise NotImplementedError()


class GetFeatureOutputRenderer(OutputRenderer):
    """Additional base class for outputs of GetFeature.

    This maps some common elements to avoid duplication.
    """

    #: Whether the output format needs a number_matched in the context data
    needs_number_matched = False

    def __init__(self, method: WFSMethod, context: dict, **params):
        # Common elements for GetFeature output:
        self.server_url = method.view.server_url
        self.app_xml_namespace = method.view.xml_namespace
        self.timestamp = now().astimezone(utc).isoformat()

        # Extract some context
        self.output_crs = context["output_crs"]

        super().__init__(method, context, **params)

    def get_context_data(self, **context):
        """Improve the context for XML output."""
        if not self.needs_number_matched:
            return context

        # For GML/XML, it's not possible the stream the queryset results
        # as the first tag needs to describe the number of results.
        feature_collections = [
            (feature, list(qs), matched)
            for feature, qs, matched in context["feature_collections"]
        ]

        context["feature_collections"] = feature_collections
        context["number_returned"] = sum(len(qs) for _, qs, _ in feature_collections)
        context["bounding_box"] = self.get_bounding_box(feature_collections)
        return context

    def render_stream(self):
        """Render the XML as streaming content"""
        # This is just a convenience approach for various common parameters:
        return self.render_get_feature(
            feature_collections=self.context["feature_collections"],
            number_matched=self.context.get("number_matched"),
            number_returned=self.context.get("number_returned"),
            next=self.context.get("next"),
            previous=self.context.get("previous"),
        )

    def render_get_feature(
        self, feature_collections, number_matched, number_returned, next, previous
    ):
        """Implement this in subclasses to write the proper output"""
        raise NotImplementedError()

    def get_bounding_box(self, feature_collections) -> BoundingBox:
        """Determine bounding box of all items."""

        # Start with an obviously invalid bbox,
        # which corrects at the first extend_to_geometry call.
        bbox = BoundingBox(math.inf, math.inf, -math.inf, -math.inf)
        for feature, qs, matched in feature_collections:
            for instance in qs:
                geomery_value = getattr(instance, feature.geometry_field_name)
                if geomery_value is None:
                    continue

                bbox.extend_to_geometry(geomery_value)

        return bbox


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
