from __future__ import annotations

import logging
import math
import typing
from io import BytesIO, StringIO

from django.conf import settings
from django.db import models
from django.http import HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase  # Django 3.2 import location

from gisserver.types import XsdAnyType, XsdNode

from .utils import to_qname

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from gisserver.operations.base import WFSMethod
    from gisserver.projection import FeatureProjection, FeatureRelation

    from .results import FeatureCollection


class OutputRenderer:
    """Base class for rendering content.
    This also provides logic to translate XML elements into aliases named,
    as nearly all responses include writing XML.
    """

    #: Default content type for the HTTP response
    content_type = "text/xml; charset=utf-8"

    #: Default extra namespaces to include in the xmlns="..." attributes, and use for to_qname().
    xml_namespaces = {}

    def __init__(self, method: WFSMethod):
        """Base method for all output rendering."""
        self.method = method
        self.server_url = method.view.server_url
        self.app_namespaces = {
            **self.xml_namespaces,
            **method.view.get_xml_namespaces_to_prefixes(),
        }

    @property
    def xmlns_attributes(self):
        """Render XML Namespace declaration attributes"""
        return self.render_xmlns_attributes(self.app_namespaces)

    def render_xmlns_attributes(self, app_namespaces: dict[str, str]) -> str:
        """Render XML Namespace declaration attributes"""
        return " ".join(
            f'xmlns:{prefix}="{xml_namespace}"' if prefix else f'xmlns="{xml_namespace}"'
            for xml_namespace, prefix in app_namespaces.items()
        )

    def to_qname(self, xsd_type: XsdNode | XsdAnyType, namespaces=None) -> str:
        """Generate the aliased name for the element."""
        return to_qname(xsd_type.namespace, xsd_type.name, namespaces or self.app_namespaces)

    def get_response(self) -> HttpResponseBase:
        """Render the output as regular or streaming response."""
        stream = self.render_stream()
        if isinstance(stream, (str, bytes, StringIO, BytesIO)):
            # Not a real stream, output anyway as regular HTTP response.
            response = HttpResponse(content=stream, content_type=self.content_type)
        else:
            # An actual generator.
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


class CollectionOutputRenderer(OutputRenderer):
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

    def __init__(self, method: WFSMethod, collection: FeatureCollection):
        """
        Receive the collected data to render.

        :param method: The calling WFS Method (e.g. GetFeature class)
        :param collection: The collected data for rendering.
        """
        super().__init__(method)
        self.collection = collection
        self.apply_projection()

    def apply_projection(self):
        """Perform presentation-layer logic enhancements on the queryset."""
        for sub_collection in self.collection.results:
            queryset = self.decorate_queryset(
                projection=sub_collection.projection,
                queryset=sub_collection.queryset,
            )
            if sub_collection._result_cache is not None:
                raise RuntimeError(
                    "SimpleFeatureCollection QuerySet was already processed in output rendering."
                )
            if queryset is not None:
                sub_collection.queryset = queryset

    def decorate_queryset(
        self, projection: FeatureProjection, queryset: models.QuerySet
    ) -> models.QuerySet:
        """Apply presentation layer logic to the queryset.

        This allows fine-tuning the queryset for any special needs of the output rendering type.

        :param feature_type: The feature that is being queried.
        :param queryset: The constructed queryset so far.
        :param output_crs: The projected output
        """
        if queryset._result_cache is not None:
            raise RuntimeError(
                "QuerySet was already processed before passing to the output rendering."
            )

        # Avoid fetching relations, fetch these within the same query,
        prefetches = self._get_prefetch_related(projection)
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

    def _get_prefetch_related(self, projection: FeatureProjection) -> list[models.Prefetch]:
        """Summarize which fields read data from relations.

        This combines the input from flattened and complex fields,
        in the unlikely case both variations are used in the same feature.
        """
        # When PROPERTYNAME is used, determine all ORM paths (and levels) that this query will touch.
        # The prefetch will only be applied when its field coincide with this list.

        return [
            models.Prefetch(
                orm_relation.orm_path,
                queryset=self.get_prefetch_queryset(projection, orm_relation),
            )
            for orm_relation in projection.orm_relations
        ]

    def get_prefetch_queryset(
        self, projection: FeatureProjection, feature_relation: FeatureRelation
    ) -> models.QuerySet | None:
        """Generate a custom queryset that's used to prefetch a relation."""
        # Multiple elements could be referencing the same model, just take first that is filled in.
        if feature_relation.related_model is None:
            return None

        # This will also apply .only() based on the projection's feature_relation
        return projection.feature_type.get_related_queryset(feature_relation)

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
                    typenames="+".join(
                        feature_type.name
                        for sub in self.collection.results
                        for feature_type in sub.feature_types
                    ),
                    page=page,
                    date=self.collection.date.strftime("%Y-%m-%d %H.%M.%S%z"),
                    timestamp=self.collection.timestamp,
                )
            }

        return {}
