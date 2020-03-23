"""Operations that implement the WFS 2.0 spec.

Useful docs:
* http://portal.opengeospatial.org/files/?artifact_id=39967
* https://www.opengeospatial.org/standards/wfs#downloads
* http://schemas.opengis.net/wfs/2.0/
* https://mapserver.org/development/rfc/ms-rfc-105.html
* https://enonline.supermap.com/iExpress9D/API/WFS/WFS200/WFS_2.0.0_introduction.htm
"""
import logging
import re
from typing import List
from urllib.parse import urlencode

from django.core.exceptions import FieldError
from django.db import ProgrammingError

from gisserver.exceptions import InvalidParameterValue, VersionNegotiationFailed
from gisserver.features import FeatureType
from gisserver.parsers import fes20, queries
from gisserver.parsers.fes20 import expressions
from gisserver.types import BoundingBox, CRS

from .base import (
    OutputFormat,
    Parameter,
    WFSMethod,
    WFSTypeNamesMethod,
    UnsupportedParameter,
)
from gisserver import output

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
            "service_constraints": self.view.service_constraints,
            "filter_capabilities": self.view.filter_capabilities,
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

    output_formats = [
        OutputFormat("XMLSCHEMA"),
        # OutputFormat("text/xml", subtype="gml/3.1.1"),
    ]
    xml_template_name = "describe_feature_type.xml"
    xml_content_type = "application/gml+xml; version=3.2"  # mandatory for WFS

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

    parameters = [Parameter("STOREDQUERY_ID", parser=lambda v: v.split(","))]

    def get_context_data(self, **params):
        if params["STOREDQUERY_ID"] is not None:
            for q in params["STOREDQUERY_ID"]:
                raise InvalidParameterValue(
                    "storedqueryid", f"Unknown stored query id: {q}"
                )

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
        UnsupportedParameter("resourceID"),  # query on ID (called featureID in wfs 1.x)
        UnsupportedParameter("aliases"),
    ]

    def get_context_data(self, resultType, **params):
        query_expression = self.get_query(**params)
        querysets = self.get_querysets(query_expression, **params)

        if resultType == "HITS":
            collection = self.get_hits(querysets)
        elif resultType == "RESULTS":
            collection = self.get_paginated_results(querysets, **params)
        else:
            raise NotImplementedError()

        # These become init kwargs for the selected OutputRenderer class:
        return {
            "collection": collection,
            "output_crs": params["srsName"] or params["typeNames"][0].crs,
        }

    def get_query(self, **params) -> queries.QueryExpression:
        """Create the query object that will process this request"""
        return queries.AdhocQuery.from_kvp_request(**params)

    def get_hits(self, querysets) -> output.FeatureCollection:
        """Return the number of hits"""
        return output.FeatureCollection(
            results=[], number_matched=sum([qs.count() for qs in querysets])
        )

    def get_paginated_results(self, querysets, **params) -> output.FeatureCollection:
        """Handle pagination settings."""
        max_page_size = self.view.max_page_size
        start = max(0, params["startIndex"])
        page_size = min(max_page_size, params["count"] or max_page_size)
        stop = start + page_size

        # The querysets are not executed until the very end.
        results = [
            output.SimpleFeatureCollection(qs.feature_type, qs, start, stop)
            for qs in querysets
        ]

        try:
            number_matched = sum(collection.number_matched for collection in results)
        except ProgrammingError as e:
            # e.g. comparing datetime against integer
            self._log_filter_error(logging.WARNING, e, params["filter"])
            raise InvalidParameterValue(
                "filter",
                "Invalid filter query, check the used datatypes and field names.",
            ) from e

        previous = next = None
        if start > 0:
            previous = self._replace_url_params(STARTINDEX=max(0, start - page_size))
        if stop < number_matched:  # TODO: fix for returning multiple typeNames
            next = self._replace_url_params(STARTINDEX=start + page_size)

        return output.FeatureCollection(
            results=results, number_matched=number_matched, next=next, previous=previous
        )

    def get_querysets(self, query_expression, typeNames, **params):
        """Generate querysets for all requested data."""
        results = []
        for feature_type in typeNames:
            try:
                queryset = self.get_queryset(feature_type, query_expression, **params)
            except FieldError as e:
                # e.g. doing a LIKE on a foreign key
                self._log_filter_error(logging.ERROR, e, params["filter"])
                raise InvalidParameterValue(
                    "filter", f"Internal error when processing filter",
                ) from e
            except (ValueError, TypeError) as e:
                raise InvalidParameterValue(
                    "filter", f"Invalid filter query: {e}",
                ) from e

            queryset.feature_type = feature_type
            results.append(queryset)

        return results

    def get_queryset(self, feature_type: FeatureType, query_expression, **params):
        """Generate the queryset for a single feature."""
        fes_query = query_expression.get_fes_query(feature_type)
        queryset = feature_type.get_queryset()
        return fes_query.filter_queryset(queryset)

    def _log_filter_error(self, level, exc, filter: fes20.Filter):
        """Report a filtering parsing error in the logging"""
        fes_xml = filter.source if filter is not None else "(not provided)"
        try:
            sql = exc.__cause__.cursor.query.decode()
        except AttributeError:
            logger.log(level, "WFS query failed: %s\nFilter:\n%s", exc, fes_xml)
        else:
            logger.log(
                level,
                "WFS query failed: %s\nSQL Query: %s\n\nFilter:\n%s",
                exc,
                sql,
                fes_xml,
            )

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
            "text/xml", subtype="gml/3.2", renderer_class=output.GML32Renderer
        ),
        # OutputFormat("gml"),
        OutputFormat(
            "application/json",
            subtype="geojson",
            charset="utf-8",
            renderer_class=output.GeoJsonRenderer,
        ),
        # OutputFormat("text/csv"),
        # OutputFormat("shapezip"),
        # OutputFormat("application/zip"),
    ]


class GetPropertyValue(BaseWFSPresentationMethod):
    """This returns a limited set of properties of the feature.
    It works almost identical to GetFeature, except that it returns a single field.
    """

    output_formats = [
        OutputFormat(
            "text/xml", subtype="gml/3.2", renderer_class=output.GML32ValueRenderer
        ),
    ]

    parameters = BaseWFSPresentationMethod.parameters + [
        Parameter("valueReference", required=True, parser=expressions.ValueReference)
    ]

    def get_queryset(self, feature_type: FeatureType, adhoc_query, **params):
        """Generate the queryset that returns only the value reference."""
        fes_query = adhoc_query.get_fes_query(feature_type)
        queryset = feature_type.get_queryset()
        value_reference: expressions.ValueReference = params["valueReference"]

        # TODO: for now only check direct field names, no xpath (while query support it)
        if value_reference.element_name not in feature_type.fields:
            raise InvalidParameterValue(
                "valueReference", f"Field '{value_reference.xpath}' does not exist.",
            )

        # Adjust FesQuery to query for the selected propety
        field = fes_query.add_value_reference(value_reference)
        queryset = fes_query.filter_queryset(queryset)

        # Only return those values
        return queryset.values("pk", member=field)

    def get_context_data(self, **params):
        context = super().get_context_data(**params)
        context["value_reference"] = params["valueReference"]
        return context
