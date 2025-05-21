from __future__ import annotations

import logging
import math
import typing
from collections.abc import Iterator
from io import BytesIO, StringIO
from itertools import chain

from django.conf import settings
from django.db import models
from django.http import HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase  # Django 3.2 import location

from gisserver.exceptions import wrap_filter_errors
from gisserver.features import FeatureType
from gisserver.parsers.values import fix_type_name
from gisserver.parsers.xml import split_ns
from gisserver.types import XsdAnyType, XsdNode

from .utils import render_xmlns_attributes, to_qname

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from gisserver.operations.base import WFSOperation
    from gisserver.projection import FeatureProjection, FeatureRelation

    from .results import FeatureCollection, SimpleFeatureCollection


class OutputRenderer:
    """Base class for rendering content.

    Note most rendering logic will generally
    need to use :class:`~gisserver.output.XmlOutputRenderer`
    or :class:`~gisserver.output.CollectionOutputRenderer` as their base class
    """

    #: Default content type for the HTTP response
    content_type = "application/octet-stream"

    def __init__(self, operation: WFSOperation):
        """Base method for all output rendering."""
        self.operation = operation

    def get_response(self) -> HttpResponseBase:
        """Render the output as regular or streaming response."""
        stream = self.render_stream()
        if isinstance(stream, (str, bytes, StringIO, BytesIO)):
            # Not a real stream, output anyway as regular HTTP response.
            return HttpResponse(
                content=stream,
                content_type=self.content_type,
                headers=self.get_headers(),
            )
        else:
            # An actual generator.
            # Peek the generator so initial exceptions can still be handled,
            # and get rendered as normal HTTP responses with the proper status.
            try:
                start = next(stream)  # peek, so any raised OWSException here is handled by OWSView
                stream = chain([start], self._trap_exceptions(stream))
            except StopIteration:
                pass

            # Handover to WSGI server (starts streaming when reading the contents)
            return StreamingHttpResponse(
                streaming_content=stream,
                content_type=self.content_type,
                headers=self.get_headers(),
            )

    def get_headers(self) -> dict[str, str]:
        """Override to define HTTP headers to add."""
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
        """Implement this in subclasses to implement a custom output format.

        The implementation may return a ``str``/``bytes`` object, which becomes
        a normal ``HttpResponse`` object **OR** return a generator
        that emits chunks. Such generator is wrapped in a ``StreamingHttpResponse``.
        """
        raise NotImplementedError()


class XmlOutputRenderer(OutputRenderer):
    """Base class/mixin for XML-based rendering.

    This provides the logic to translate XML elements into QName aliases.
    """

    #: Default content type for the HTTP response
    content_type = "text/xml; charset=utf-8"

    #: Default extra namespaces to include in the xmlns="..." attributes, and use for to_qname().
    xml_namespaces = {}

    def __init__(self, operation: WFSOperation):
        """Base method for all output rendering."""
        super().__init__(operation)
        self.app_namespaces = {
            **self.xml_namespaces,
            **operation.view.get_xml_namespaces_to_prefixes(),
        }

    def render_xmlns_attributes(self):
        """Render XML Namespace declaration attributes"""
        return render_xmlns_attributes(self.app_namespaces)

    def to_qname(self, xsd_type: XsdNode | XsdAnyType, namespaces=None) -> str:
        """Generate the aliased name for the element or type."""
        return to_qname(xsd_type.namespace, xsd_type.name, namespaces or self.app_namespaces)

    def feature_to_qname(self, feature_type: FeatureType | str) -> str:
        """Convert the FeatureType name to a QName"""
        if isinstance(feature_type, FeatureType):
            return to_qname(feature_type.xml_namespace, feature_type.name, self.app_namespaces)
        else:
            # e.g. "return_type" for StoredQueryDescription/QueryExpressionText
            type_name = fix_type_name(feature_type, self.operation.view.xml_namespace)
            ns, localname = split_ns(type_name)
            return to_qname(ns, localname, self.app_namespaces)


class CollectionOutputRenderer(OutputRenderer):
    """Base class to create streaming responses."""

    #: Allow to override the maximum page size.
    #: This value can be 'math.inf' to support endless pages by default.
    max_page_size = None

    #: An optional content-disposition header to output
    content_disposition = None

    def __init__(self, operation: WFSOperation, collection: FeatureCollection):
        """
        Receive the collected data to render.

        :param operation: The calling WFS Operation (e.g. GetFeature class)
        :param collection: The collected data for rendering.
        """
        super().__init__(operation)
        self.collection = collection
        self.apply_projection()

    def apply_projection(self):
        """Perform presentation-layer logic enhancements on all results.
        This calls :meth:`decorate_queryset` for
        each :class:`~gisserver.output.SimpleFeatureCollection`.
        """
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

        :param projection: The projection information, including feature that is being rendered.
        :param queryset: The constructed queryset so far.
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
            return {
                "Content-Disposition": self.content_disposition.format(
                    **self.get_content_disposition_kwargs()
                )
            }

        return {}

    def get_content_disposition_kwargs(self) -> dict:
        """Offer a common quick content-disposition logic that works for all possible queries."""
        sub_collection = self.collection.results[0]
        if sub_collection.stop == math.inf:
            page = f"{sub_collection.start}-end" if sub_collection.start else "all"
        elif sub_collection.stop:
            page = f"{sub_collection.start}-{sub_collection.stop - 1}"
        else:
            page = "results"

        return {
            "typenames": "+".join(
                feature_type.name
                for sub in self.collection.results
                for feature_type in sub.feature_types
            ),
            "page": page,
            "date": self.collection.date.strftime("%Y-%m-%d %H.%M.%S%z"),
            "timestamp": self.collection.timestamp,
        }

    def read_features(self, sub_collection: SimpleFeatureCollection) -> Iterator[models.Model]:
        """A wrapper to read features from a collection, while raising WFS exceptions on query errors."""
        with wrap_filter_errors(sub_collection.source_query):
            yield from sub_collection
