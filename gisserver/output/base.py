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

    def __init__(self, method: WFSMethod, context: dict, **params):
        # Common elements for GetFeature output:
        self.server_url = method.view.server_url
        self.app_xml_namespace = method.view.xml_namespace
        self.timestamp = now().astimezone(utc).isoformat()

        # Extract some context
        self.output_crs = context["output_crs"]

        super().__init__(method, context, **params)

    def render_stream(self):
        """Render the XML as streaming content"""
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
