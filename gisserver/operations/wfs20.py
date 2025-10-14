"""Operations that implement the WFS 2.0 specification.

These operations are called by the :class:`~gisserver.views.WFSView`,
and receive the request that was parsed using :mod:`gisserver.parsers.wfs20`.
Thus, there is nearly no difference between GET/POST requests here.

In a way this looks like an MVC (Model-View-Controller) design:

* :mod:`gisserver.parsers.wfs20` parsed the request, and provides the "model".
* :mod:`gisserver.operations.wfs20` orchestrates here what to do (the controller).
* :mod:`gisserver.output` performs the rendering (the view).
"""

from __future__ import annotations

import logging
import math
import re
import typing
from urllib.parse import urlencode

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from gisserver import conf, output
from gisserver.exceptions import (
    InvalidParameterValue,
    VersionNegotiationFailed,
    wrap_filter_errors,
)
from gisserver.extensions.functions import function_registry
from gisserver.extensions.queries import stored_query_registry
from gisserver.features import FeatureType
from gisserver.output import CollectionOutputRenderer
from gisserver.parsers import ows, wfs20

from .base import OutputFormat, OutputFormatMixin, Parameter, WFSOperation, XmlTemplateMixin

logger = logging.getLogger(__name__)

SAFE_VERSION = re.compile(r"\A[0-9.]+\Z")
RE_SAFE_FILENAME = re.compile(r"\A[A-Za-z0-9]+[A-Za-z0-9.]*")  # no dot at the start.

__all__ = [
    "GetCapabilities",
    "DescribeFeatureType",
    "BaseWFSGetDataOperation",
    "GetFeature",
    "GetPropertyValue",
    "ListStoredQueries",
    "DescribeStoredQueries",
]


class GetCapabilities(XmlTemplateMixin, OutputFormatMixin, WFSOperation):
    """This operation returns map features, and available operations this WFS server supports."""

    ows_request: wfs20.GetCapabilities

    xml_template_name = "get_capabilities.xml"

    def get_output_formats(self):
        return [
            OutputFormat("text/xml", renderer_class=None),
            OutputFormat(
                # for FME (Feature Manipulation Engine)
                "application/gml+xml",
                renderer_class=None,
                version="3.2",
                title="GML",
                in_capabilities=False,
            ),
        ]

    def get_parameters(self):
        # Not calling super, as this differs slightly (not requiring VERSION)
        return [
            Parameter("service", allowed_values=list(self.view.accept_operations.keys())),
            Parameter("AcceptVersions", allowed_values=self.view.accept_versions),
            Parameter("AcceptFormats", allowed_values=[str(o) for o in self.get_output_formats()]),
        ]

    def validate_request(self, ows_request: wfs20.GetCapabilities):
        # Validate AcceptVersions
        self._parse_accept_versions(ows_request)

        # Validate AcceptFormats
        if ows_request.acceptFormats:
            for output_format in ows_request.acceptFormats:
                self.resolve_output_format(output_format, locator="AcceptFormats")

    def _parse_accept_versions(self, ows_request: wfs20.GetCapabilities) -> str | None:
        """Special parsing for the ACCEPTVERSIONS parameter."""
        if not ows_request.acceptVersions:
            return None

        matched_versions = set(ows_request.acceptVersions).intersection(self.view.accept_versions)
        if not matched_versions:
            allowed = ", ".join(self.view.accept_versions)
            raise VersionNegotiationFailed(
                f"'{','.join(ows_request.acceptVersions)}' does not contain supported versions, "
                f"supported are: {allowed}.",
                locator="acceptversions",
            )

        # Take the highest version (mapserver returns first matching)
        requested_version = sorted(matched_versions, reverse=True)[0]

        # Make sure the views+exceptions continue to operate in this version
        self.view.set_version(ows_request.service, requested_version)
        return requested_version

    def get_context_data(self) -> dict:
        # The 'service' is not read from 'params' to avoid dependency on get_parameters()
        service_operations = self.view.accept_operations[self.ows_request.service]
        app_namespaces = self.view.get_xml_namespaces_to_prefixes()

        get_feature_op_cls = service_operations["GetFeature"]
        feature_output_formats = get_feature_op_cls(self.view, None).get_output_formats()

        return {
            "xml_namespaces": app_namespaces,
            "service_description": self.view.get_service_description(self.ows_request.service),
            "accept_operations": {
                name: operation_class(self.view, None).get_parameters()
                for name, operation_class in service_operations.items()
            },
            "service_constraints": self.view.wfs_service_constraints,
            "filter_capabilities": self.view.wfs_filter_capabilities,
            "function_registry": function_registry,
            "accept_versions": self.view.accept_versions,
            "feature_types": self.view.get_bound_feature_types(),
            "feature_output_formats": feature_output_formats,
            "default_max_features": self.view.max_page_size,
            "BOUNDING_BOX": conf.GISSERVER_CAPABILITIES_BOUNDING_BOX,
        }


class DescribeFeatureType(OutputFormatMixin, WFSOperation):
    """This returns an XML Schema for the provided objects.
    Each feature is exposed as an XSD definition with its fields.
    """

    ows_request: wfs20.DescribeFeatureType

    def get_output_formats(self):
        return [
            OutputFormat("XMLSCHEMA", renderer_class=output.XmlSchemaRenderer),
            # At least one version of FME (Feature Manipulation Engine) seems to
            # send a DescribeFeatureType request with this GML as output format.
            # Do what mapserver does and just send it XML Schema.
            # This output format also seems to be used in the WFS 2.0.2 spec!
            OutputFormat(
                "application/gml+xml",
                version="3.2",
                renderer_class=output.XmlSchemaRenderer,
                in_capabilities=False,
            ),
            # OutputFormat("text/xml", subtype="gml/3.1.1"),
        ]

    def validate_request(self, ows_request: wfs20.DescribeFeatureType):
        if not ows_request.typeNames:
            self.feature_types = self.view.get_bound_feature_types()
        else:
            self.feature_types = [
                self.resolve_feature_type(type_name) for type_name in ows_request.typeNames
            ]
        self.output_format = self.resolve_output_format(ows_request.outputFormat)

    def process_request(self, ows_request: wfs20.DescribeFeatureType):
        renderer_class = self.output_format.renderer_class or output.XmlSchemaRenderer
        renderer = renderer_class(self, self.feature_types)
        return renderer.get_response()


class ListStoredQueries(WFSOperation):
    """This describes the available queries"""

    ows_request: wfs20.ListStoredQueries

    def process_request(self, ows_request: ows.BaseOwsRequest):
        renderer = output.ListStoredQueriesRenderer(
            self,
            query_descriptions=stored_query_registry.get_queries(),
        )
        return renderer.get_response()


class DescribeStoredQueries(WFSOperation):
    """This describes the available queries"""

    ows_request: wfs20.DescribeStoredQueries

    def validate_request(self, ows_request: wfs20.DescribeStoredQueries):
        if ows_request.storedQueryId is None:
            self.query_descriptions = stored_query_registry.get_queries()
        else:
            self.query_descriptions = [
                stored_query_registry.resolve_query(query_id)
                for query_id in ows_request.storedQueryId
            ]

    def process_request(self, ows_request: ows.BaseOwsRequest):
        renderer = output.DescribeStoredQueriesRenderer(self, self.query_descriptions)
        return renderer.get_response()


class BaseWFSGetDataOperation(OutputFormatMixin, WFSOperation):
    """Base class for GetFeature / GetPropertyValue"""

    ows_request: wfs20.GetFeature | wfs20.GetPropertyValue

    if typing.TYPE_CHECKING:
        # Tell the type checker subclasses will only work with CollectionOutputRenderer rendering.

        def resolve_output_format(
            self, value, locator="outputFormat"
        ) -> OutputFormat[CollectionOutputRenderer]:
            return super().resolve_output_format(value, locator=locator)

    def get_parameters(self) -> list[Parameter]:
        """Parameters to advertise in the capabilities for this method."""
        return [
            # Advertise parameters in GetCapabilities
            Parameter("resultType", allowed_values=["RESULTS", "HITS"]),
            Parameter("resolve", allowed_values=["local"]),
        ]

    def validate_request(self, ows_request: wfs20.GetFeature | wfs20.GetPropertyValue):
        """Validate the incoming data before execution."""
        self.output_format = self.resolve_output_format(ows_request.outputFormat)

        # Resolve the feature types
        # Allow these to skip, e.g. when the query needs to return 0 results (GetFeatureById).
        for query in ows_request.queries:
            type_names = query.get_type_names()
            feature_types = [
                self.resolve_feature_type(
                    type_name,
                    locator=("resourceId" if query.query_locator == "resourceId" else "typeNames"),
                )
                for type_name in type_names
            ]
            self.bind_query(query, feature_types)

            # Allow both the view and feature-type to check for access.
            # Before 2.0 only FeatureType classes offered this, which required subclassing
            # FeatureType to access view.request.user. The direct view check avoids that need.
            for feature_type in feature_types:
                self.view.check_permissions(feature_type)
                feature_type.check_permissions(self.view.request)

    def bind_query(self, query: wfs20.QueryExpression, feature_types: list[FeatureType]):
        """Allow to be overwritten in GetFeatureValue"""
        query.bind(feature_types)

    def process_request(self, ows_request: wfs20.GetFeature | wfs20.GetPropertyValue):
        """Process the query, and generate the output."""
        # Initialize the collection, which constructs the ORM querysets.
        if ows_request.resultType == wfs20.ResultType.hits:
            collection = self.get_hits()
        elif self.ows_request.resultType == wfs20.ResultType.results:
            collection = self.get_results()
        else:
            raise NotImplementedError()

        # assert False, str(collection.results[0].queryset.query)

        # Initialize the renderer.
        # This can also decorate the querysets with projection information,
        # such as converting geometries to the correct CRS or add prefetch_related logic.
        renderer = self.output_format.renderer_class(operation=self, collection=collection)

        # Fixing pagination will invoke the query,
        # hence this is done at the end
        self.set_pagination_links(collection)

        # Render it!
        return renderer.get_response()

    def get_hits(self) -> output.FeatureCollection:
        """Handle the resultType=hits query.
        This creates the QuerySet and counts the number of results.
        """
        start, count = self.get_pagination()
        results = []
        for query in self.ows_request.queries:
            with wrap_filter_errors(query):
                queryset = query.get_queryset()

            results.append(
                output.SimpleFeatureCollection(
                    source_query=query,
                    feature_types=query.feature_types,
                    queryset=queryset.none(),
                    start=start,
                    stop=start + count,  # yes, count can be passed for hits
                    number_matched=queryset.count(),
                )
            )

        return output.FeatureCollection(
            results=results,
            number_matched=sum(r.number_matched for r in results),
        )

    def get_results(self) -> output.FeatureCollection:
        """Handle the resultType=results query.
        This creates the queryset, allowing to read over all results.
        """
        start, count = self.get_pagination()
        results = []
        for query in self.ows_request.queries:
            # The querysets are not executed yet, until the output is reading them.
            with wrap_filter_errors(query):
                queryset = query.get_queryset()

            results.append(
                output.SimpleFeatureCollection(
                    source_query=query,
                    feature_types=query.feature_types,
                    queryset=queryset,
                    start=start,
                    stop=start + count,
                )
            )

        # number_matched is not given here, so some rendering formats can count it instead.
        # For GML it need to be printed at the start, but for GeoJSON it can be rendered
        # as the last bit of the response. That avoids performing an expensive COUNT query.
        return output.FeatureCollection(results=results)

    def get_pagination(self) -> tuple[int, int]:
        """Tell what the requested page size is."""
        start = max(0, self.ows_request.startIndex)

        # outputFormat.max_page_size can be math.inf to enable endless scrolling.
        # this only works when the COUNT parameter is not given.
        max_page_size = self.output_format.max_page_size or self.view.max_page_size
        default_page_size = (
            0 if self.ows_request.resultType == wfs20.ResultType.hits else max_page_size
        )
        count = min(max_page_size, self.ows_request.count or default_page_size)
        return start, count

    def set_pagination_links(self, collection: output.FeatureCollection):
        """Assign the pagination links to the collection.
        This happens within the operation logic, as it can access the original GET request.
        """
        if self.ows_request.resultType == wfs20.ResultType.hits and not self.ows_request.count:
            return

        start, count = self.get_pagination()
        stop = start + count
        if stop != math.inf:
            if start > 0:
                collection.previous = self._replace_url_params(
                    STARTINDEX=max(0, start - count),
                    COUNT=count,
                )

            # Note that reading collection.has_next will invoke the query!
            if collection.has_next:
                # TODO: fix this when returning multiple typeNames:
                collection.next = self._replace_url_params(
                    STARTINDEX=start + count,
                    COUNT=count,
                )

    def _replace_url_params(self, **updates) -> str | None:
        """Replace a query parameter in the URL"""
        new_params = self.view.request.GET.copy()  # preserve lowercase fields too
        if self.view.request.method != "GET":
            # CITE compliance testing wants to see a 'next' link for POST requests too.
            try:
                new_params.update(self.ows_request.as_kvp())
            except NotImplementedError:
                # Various POST requests can't be translated back to KVP
                # mapserver omits the 'next' link in these cases too.
                return None

        # Replace any lower/mixed case variants of the previous names:
        for name in new_params:
            upper = name.upper()
            if upper in updates:
                new_params[name] = updates.pop(upper)

        # Override/replace with new remaining uppercase variants
        new_params.update(updates)
        return f"{self.view.server_url}?{urlencode(new_params)}"


class GetFeature(BaseWFSGetDataOperation):
    """This returns all properties of the feature.

    Various query parameters allow limiting the data.
    """

    def get_output_formats(self) -> list[OutputFormat]:
        """Return the default output formats.
        This selects a different rendering depending on the ``GISSERVER_USE_DB_RENDERING`` setting.
        """
        if conf.GISSERVER_GET_FEATURE_OUTPUT_FORMATS:
            return self.get_custom_output_formats(
                conf.GISSERVER_GET_FEATURE_OUTPUT_FORMATS | conf.GISSERVER_EXTRA_OUTPUT_FORMATS
            )

        if conf.GISSERVER_USE_DB_RENDERING:
            csv_renderer = output.DBCSVRenderer
            gml32_renderer = output.DBGML32Renderer
            geojson_renderer = output.DBGeoJsonRenderer
        else:
            csv_renderer = output.CSVRenderer
            gml32_renderer = output.GML32Renderer
            geojson_renderer = output.GeoJsonRenderer

        return [
            OutputFormat(
                # Needed for cite compliance tests
                "application/gml+xml",
                version="3.2",
                renderer_class=gml32_renderer,
                title="GML",
            ),
            OutputFormat(
                "text/xml",
                subtype="gml/3.2.1",
                renderer_class=gml32_renderer,
                title="GML 3.2.1",
            ),
            # OutputFormat("gml"),
            OutputFormat(
                # identical to mapserver:
                "application/json",
                subtype="geojson",
                charset="utf-8",
                renderer_class=geojson_renderer,
                title="GeoJSON",
            ),
            OutputFormat(
                # Alias needed to make ESRI ArcGIS online accept the WFS.
                # It does not recognize the "subtype" as an alias.
                "geojson",
                renderer_class=geojson_renderer,
            ),
            OutputFormat(
                "text/csv",
                subtype="csv",
                charset="utf-8",
                renderer_class=csv_renderer,
                title="CSV",
            ),
            # OutputFormat("shapezip"),
            # OutputFormat("application/zip"),
        ] + self.get_custom_output_formats(conf.GISSERVER_EXTRA_OUTPUT_FORMATS)

    def get_custom_output_formats(self, output_formats_setting: dict) -> list[OutputFormat]:
        """Add custom output formats defined in the settings."""
        result = []
        for content_type, format_kwargs in output_formats_setting.items():
            renderer_class = format_kwargs["renderer_class"]
            if isinstance(renderer_class, str):
                format_kwargs["renderer_class"] = import_string(renderer_class)

            if not issubclass(renderer_class, CollectionOutputRenderer):
                raise ImproperlyConfigured(
                    f"The 'renderer_class' of output format {content_type!r},"
                    f" should be a subclass of CollectionOutputRenderer."
                )

            result.append(OutputFormat(content_type, **format_kwargs))

        return result

    def get_parameters(self) -> list[Parameter]:
        """Extend Parameters with outputFormat to support ArcGISOnline."""
        parameters = super().get_parameters()

        return parameters + [
            Parameter("outputFormat", allowed_values=self.get_output_formats()),
        ]


class GetPropertyValue(BaseWFSGetDataOperation):
    """This returns a limited set of properties of the feature.
    It works almost identical to GetFeature, except that it returns a single field.
    """

    ows_request: wfs20.GetPropertyValue

    def get_output_formats(self) -> list[OutputFormat]:
        """Define the output format for GetPropertyValue."""
        gml32_value_renderer = (
            output.DBGML32ValueRenderer
            if conf.GISSERVER_USE_DB_RENDERING
            else output.GML32ValueRenderer
        )

        return [
            OutputFormat(
                "application/gml+xml",
                version="3.2",
                renderer_class=gml32_value_renderer,
                title="GML",
            ),
            OutputFormat("text/xml", subtype="gml/3.2", renderer_class=gml32_value_renderer),
        ]

    def validate_request(self, ows_request: wfs20.GetPropertyValue):
        super().validate_request(ows_request)

        if ows_request.resolvePath:
            raise InvalidParameterValue(
                "Support for resolvePath is not implemented!", locator="resolvePath"
            )

    def bind_query(self, query: wfs20.QueryExpression, feature_types: list[FeatureType]):
        """Allow to be overwritten in GetFeatureValue"""
        # Pass valueReference to the query, which will include it in the FeatureProjection.
        # In the WFS-spec, the valueReference is only a presentation layer change.
        # However, in our case AdhocQuery object also performs internal processing,
        # so the query performs a "SELECT id, <fieldname>" as well.
        query.bind(feature_types, value_reference=self.ows_request.valueReference)
