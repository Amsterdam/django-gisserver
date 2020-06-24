"""Operations that implement the WFS 2.0 spec.

Useful docs:
* http://portal.opengeospatial.org/files/?artifact_id=39967
* https://www.opengeospatial.org/standards/wfs#downloads
* http://schemas.opengis.net/wfs/2.0/
* https://mapserver.org/development/rfc/ms-rfc-105.html
* https://enonline.supermap.com/iExpress9D/API/WFS/WFS200/WFS_2.0.0_introduction.htm
"""
import math

import logging
import re
from typing import List
from urllib.parse import urlencode

from gisserver import output, queries
from gisserver.exceptions import InvalidParameterValue, VersionNegotiationFailed
from gisserver.geometries import BoundingBox, CRS
from gisserver.parsers import fes20

from .base import (
    OutputFormat,
    Parameter,
    WFSMethod,
    WFSTypeNamesMethod,
    UnsupportedParameter,
)

logger = logging.getLogger(__name__)

SAFE_VERSION = re.compile(r"\A[0-9.]+\Z")
RE_SAFE_FILENAME = re.compile(r"\A[A-Za-z0-9]+[A-Za-z0-9.]*")  # no dot at the start.


class GetCapabilities(WFSMethod):
    """"This operation returns map features, and available operations this WFS server supports."""

    output_formats = [OutputFormat("text/xml")]
    xml_template_name = "get_capabilities.xml"

    def get_parameters(self):
        # Not calling super, as this differs slightly (e.g. no output formats)
        return [
            Parameter(
                "service",
                required=True,
                in_capabilities=True,
                allowed_values=list(self.view.accept_operations.keys()),
            ),
            Parameter(
                # Version parameter can still be sent,
                # but not mandatory for GetCapabilities
                "version",
                allowed_values=self.view.accept_versions,
            ),
            Parameter(
                "AcceptVersions",
                in_capabilities=True,
                allowed_values=self.view.accept_versions,
                parser=self._parse_accept_versions,
            ),
            Parameter(
                "AcceptFormats",
                in_capabilities=True,
                allowed_values=self.output_formats,
                parser=self._parse_output_format,
                default=self.output_formats[0],
            ),
        ] + self.parameters

    def _parse_accept_versions(self, accept_versions) -> str:
        """Special parsing for the ACCEPTVERSIONS parameter."""
        if "VERSION" in self.view.KVP:
            # Even GetCapabilities can still receive a VERSION argument to fixate it.
            raise InvalidParameterValue(
                "AcceptVersions", "Can't provide both ACCEPTVERSIONS and VERSION"
            )

        matched_versions = set(accept_versions.split(",")).intersection(
            self.view.accept_versions
        )
        if not matched_versions:
            allowed = ", ".join(self.view.accept_versions)
            raise VersionNegotiationFailed(
                "acceptversions",
                f"'{accept_versions}' does not contain supported versions, "
                f"supported are: {allowed}.",
            )

        # Take the highest version (mapserver returns first matching)
        requested_version = sorted(matched_versions, reverse=True)[0]

        # Make sure the views+exceptions continue to operate in this version
        self.view.set_version(requested_version)

        return requested_version

    def __call__(self, **params):
        """GetCapabilities only supports XML output"""
        context = self.get_context_data(**params)
        return self.render_xml(context, **params)

    def get_context_data(self, **params):
        view = self.view

        # The 'service' is not reaad from 'params' to avoid dependency on get_parameters()
        service = view.KVP["SERVICE"]  # is WFS
        service_operations = view.accept_operations[service]
        feature_output_formats = service_operations["GetFeature"].output_formats

        return {
            "service_description": view.get_service_description(service),
            "accept_operations": {
                name: operation(view) for name, operation in service_operations.items()
            },
            "service_constraints": self.view.wfs_service_constraints,
            "filter_capabilities": self.view.wfs_filter_capabilities,
            "function_registry": fes20.function_registry,
            "accept_versions": self.view.accept_versions,
            "feature_types": self.view.get_feature_types(),
            "feature_output_formats": feature_output_formats,
            "default_max_features": self.view.max_page_size,
        }


class DescribeFeatureType(WFSTypeNamesMethod):
    """This returns an XML Schema for the provided objects.
    Each feature is exposed as an XSD definition with it's fields.
    """

    require_type_names = True
    output_formats = [
        OutputFormat("XMLSCHEMA", renderer_class=output.XMLSchemaRenderer),
        # OutputFormat("text/xml", subtype="gml/3.1.1"),
    ]

    def get_context_data(self, typeNames, **params):
        return {"feature_types": typeNames}


class ListStoredQueries(WFSMethod):
    """This describes the available queries"""

    xml_template_name = "list_stored_queries.xml"

    def get_context_data(self, **params):
        return {"feature_types": self.view.get_feature_types()}


class DescribeStoredQueries(WFSMethod):
    """This describes the available queries"""

    xml_template_name = "describe_stored_queries.xml"

    parameters = [
        Parameter(
            "STOREDQUERY_ID",
            parser=lambda v: v.split(","),
            allowed_values=["urn:ogc:def:query:OGC-WFS::GetFeatureById"],
        )
    ]

    def get_context_data(self, **params):
        return {"feature_types": self.view.get_feature_types()}


def parse_sort_by(value) -> List[str]:
    """Parse the SORTBY parameter."""
    result = []
    for field in value.split(","):
        if " " in field:
            field, direction = field.split(" ", 1)
            # Also supporting WFS 1.0 A/D format for clients that use this.
            if direction not in {"A", "ASC", "D", "DESC"}:
                raise InvalidParameterValue(
                    "sortby", "Expect ASC/DESC ordering direction"
                )
            if direction in {"D", "DESC"}:
                field = f"-{field}"
        result.append(field)
    return result


class BaseWFSPresentationMethod(WFSTypeNamesMethod):
    """Base class for GetFeature / GetPropertyValue"""

    parameters = [
        # StandardPresentationParameters
        Parameter(
            "resultType",
            in_capabilities=True,
            parser=lambda x: x.upper(),
            allowed_values=["RESULTS", "HITS"],
            default="RESULTS",
        ),
        Parameter("startIndex", parser=int, default=0),
        Parameter("count", parser=int),  # was called maxFeatures in WFS 1.x
        # outputFormat will be added by the base class.
        # StandardResolveParameters
        UnsupportedParameter("resolve"),  # subresource settings
        UnsupportedParameter("resolveDepth"),
        UnsupportedParameter("resolveTimeout"),
        # StandardInputParameters
        Parameter("srsName", parser=CRS.from_string),
        # Projection clause parameters
        UnsupportedParameter("propertyName"),  # which fields to return
        # AdHoc Query parameters
        Parameter("bbox", parser=BoundingBox.from_string),
        Parameter(
            "filter_language",
            default=fes20.Filter.query_language,
            allowed_values=[fes20.Filter.query_language],
        ),
        Parameter("filter", parser=fes20.Filter.from_string),
        Parameter("sortBy", parser=parse_sort_by),
        Parameter("resourceID", parser=fes20.ResourceId),
        UnsupportedParameter("aliases"),
        queries.StoredQueryParameter(),
    ]

    def get_context_data(self, resultType, **params):
        query = self.get_query(**params)
        query.check_permissions(self.view.request)

        if resultType == "HITS":
            collection = self.get_hits(query)
        elif resultType == "RESULTS":
            # Validate StandardPresentationParameters
            collection = self.get_paginated_results(query, **params)
        else:
            raise NotImplementedError()

        output_crs = params["srsName"]
        if not output_crs and collection.results:
            output_crs = collection.results[0].feature_type.crs

        # These become init kwargs for the selected OutputRenderer class:
        return {
            "source_query": query,
            "collection": collection,
            "output_crs": output_crs,
        }

    def get_query(self, **params) -> queries.QueryExpression:
        """Create the query object that will process this request"""
        if params["STOREDQUERY_ID"]:
            # The 'StoredQueryParameter' already parses the input into a complete object.
            # When it's not provided, the regular Adhoc-query will be created from the KVP request.
            query = params["STOREDQUERY_ID"]
        else:
            query = queries.AdhocQuery.from_kvp_request(**params)

        # TODO: pass this in a cleaner way?
        query.bind(
            all_feature_types=self.all_feature_types_by_name,  # for GetFeatureById
            value_reference=params.get("valueReference"),  # for GetPropertyValue
        )

        return query

    def get_hits(self, query: queries.QueryExpression) -> output.FeatureCollection:
        """Return the number of hits"""
        return query.get_hits()

    def get_results(
        self, query: queries.QueryExpression, start, count
    ) -> output.FeatureCollection:
        """Return the actual results"""
        return query.get_results(start, count=count)

    def get_paginated_results(
        self, query: queries.QueryExpression, outputFormat, **params
    ) -> output.FeatureCollection:
        """Handle pagination settings."""
        start = max(0, params["startIndex"])

        # outputFormat.max_page_size can be math.inf to enable endless scrolling.
        # this only works when the COUNT parameter is not given.
        max_page_size = outputFormat.max_page_size or self.view.max_page_size
        page_size = min(max_page_size, params["count"] or max_page_size)
        stop = start + page_size

        # Perform query
        collection = self.get_results(query, start=start, count=page_size)

        # Allow presentation-layer to add extra logic.
        if outputFormat.renderer_class is not None:
            output_crs = params["srsName"]
            if not output_crs and collection.results:
                output_crs = collection.results[0].feature_type.crs

            outputFormat.renderer_class.decorate_collection(
                collection, output_crs, **params
            )

        if stop != math.inf:
            if start > 0:
                collection.previous = self._replace_url_params(
                    STARTINDEX=max(0, start - page_size), COUNT=page_size,
                )
            if stop < collection.number_matched:
                # TODO: fix this when returning multiple typeNames:
                collection.next = self._replace_url_params(
                    STARTINDEX=start + page_size, COUNT=page_size
                )

        return collection

    def _replace_url_params(self, **updates) -> str:
        """Replace a query parameter in the URL"""
        new_params = self.view.KVP.copy()
        new_params.update(updates)
        return f"{self.view.server_url}?{urlencode(new_params)}"


class GetFeature(BaseWFSPresentationMethod):
    """This returns all properties of the feature.

    Various query parameters allow limiting the data.
    """

    output_formats = [
        OutputFormat(
            "text/xml", subtype="gml/3.2", renderer_class=output.gml32_renderer
        ),
        # OutputFormat("gml"),
        OutputFormat(
            "application/json",
            subtype="geojson",
            charset="utf-8",
            renderer_class=output.geojson_renderer,
        ),
        OutputFormat(
            "text/csv",
            subtype="csv",
            charset="utf-8",
            renderer_class=output.csv_renderer,
        ),
        # OutputFormat("shapezip"),
        # OutputFormat("application/zip"),
    ]


class GetPropertyValue(BaseWFSPresentationMethod):
    """This returns a limited set of properties of the feature.
    It works almost identical to GetFeature, except that it returns a single field.
    """

    output_formats = [
        OutputFormat(
            "text/xml", subtype="gml/3.2", renderer_class=output.gml32_value_renderer
        ),
    ]

    parameters = BaseWFSPresentationMethod.parameters + [
        Parameter("valueReference", required=True, parser=fes20.ValueReference)
    ]

    def get_context_data(self, **params):
        # Pass valueReference to output format.
        # NOTE: The AdhocQuery object also performs internal processing,
        # so the query performs a "SELECT id, <fieldname>" as well.
        # In the WFS-spec, the valueReference is only a presentation layer change.
        context = super().get_context_data(**params)
        context["value_reference"] = params["valueReference"]
        return context
