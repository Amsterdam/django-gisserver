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
from django.core.exceptions import FieldError, ValidationError
from django.db import InternalError, ProgrammingError
from urllib.parse import urlencode

from gisserver import conf, output, queries
from gisserver.exceptions import (
    ExternalParsingError,
    ExternalValueError,
    InvalidParameterValue,
    MissingParameterValue,
    OperationParsingFailed,
    VersionNegotiationFailed,
)
from gisserver.geometries import BoundingBox, CRS
from gisserver.parsers import fes20
from gisserver.queries import stored_query_registry

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
            "BOUNDING_BOX": conf.GISSERVER_CAPABILITIES_BOUNDING_BOX,
        }


class DescribeFeatureType(WFSTypeNamesMethod):
    """This returns an XML Schema for the provided objects.
    Each feature is exposed as an XSD definition with it's fields.
    """

    output_formats = [
        OutputFormat("XMLSCHEMA", renderer_class=output.XMLSchemaRenderer),
        # OutputFormat("text/xml", subtype="gml/3.1.1"),
    ]

    def get_context_data(self, typeNames, **params):
        if self.view.KVP.get("TYPENAMES") == "" or self.view.KVP.get("TYPENAME") == "":
            # Using TYPENAMES= does result in an error.
            raise MissingParameterValue("typeNames", f"Empty TYPENAMES parameter")
        elif typeNames is None:
            # Not given, all types are returned
            typeNames = self.all_feature_types

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
            parser=lambda value: [
                stored_query_registry.resolve_query(name) for name in value.split(",")
            ],
        )
    ]

    def get_context_data(self, **params):
        queries = params["STOREDQUERY_ID"] or list(stored_query_registry)
        return {
            "feature_types": self.view.get_feature_types(),
            "stored_queries": [q.meta for q in queries],
        }


class BaseWFSGetDataMethod(WFSTypeNamesMethod):
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
        Parameter("count", alias="maxFeatures", parser=int),  # maxFeatures is WFS 1.x
        # outputFormat will be added by the base class.
        # StandardResolveParameters
        Parameter("resolve", allowed_values=["local"], in_capabilities=True),
        UnsupportedParameter("resolveDepth"),  # subresource settings
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
        Parameter("sortBy", parser=fes20.SortBy.from_string),
        Parameter("resourceID", parser=fes20.parse_resource_id_kvp),
        UnsupportedParameter("aliases"),
        queries.StoredQueryParameter(),
    ]

    def get_context_data(self, resultType, **params):  # noqa: C901
        query = self.get_query(**params)
        query.check_permissions(self.view.request)

        try:
            if resultType == "HITS":
                collection = self.get_hits(query)
            elif resultType == "RESULTS":
                # Validate StandardPresentationParameters
                collection = self.get_paginated_results(query, **params)
            else:
                raise NotImplementedError()
        except ExternalParsingError as e:
            # Bad input data
            self._log_filter_error(query, logging.ERROR, e)
            raise OperationParsingFailed(self._get_locator(**params), str(e),) from e
        except ExternalValueError as e:
            # Bad input data
            self._log_filter_error(query, logging.ERROR, e)
            raise InvalidParameterValue(self._get_locator(**params), str(e),) from e
        except ValidationError as e:
            # Bad input data
            self._log_filter_error(query, logging.ERROR, e)
            raise OperationParsingFailed(
                self._get_locator(**params), "\n".join(map(str, e.messages)),
            ) from e
        except FieldError as e:
            # e.g. doing a LIKE on a foreign key, or requesting an unknown field.
            if not conf.GISSERVER_WRAP_FILTER_DB_ERRORS:
                raise
            self._log_filter_error(query, logging.ERROR, e)
            raise InvalidParameterValue(
                self._get_locator(**params), f"Internal error when processing filter",
            ) from e
        except (InternalError, ProgrammingError) as e:
            # e.g. comparing datetime against integer
            if not conf.GISSERVER_WRAP_FILTER_DB_ERRORS:
                raise
            logger.error("WFS request failed: %s\nParams: %r", e, params)
            msg = str(e)
            locator = (
                "srsName" if "Cannot find SRID" in msg else self._get_locator(**params)
            )
            raise InvalidParameterValue(locator, f"Invalid request: {msg}") from e
        except (TypeError, ValueError) as e:
            # TypeError/ValueError could reference a datatype mismatch in an
            # ORM query, but it could also be an internal bug. In most cases,
            # this is already caught by XsdElement.validate_comparison().
            if self._is_orm_error(e):
                raise InvalidParameterValue(
                    self._get_locator(**params), f"Invalid filter query: {e}",
                ) from e
            raise

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

    def _is_orm_error(self, exception: Exception):
        traceback = exception.__traceback__
        while traceback.tb_next is not None:
            traceback = traceback.tb_next
            if "/django/db/models/query" in traceback.tb_frame.f_code.co_filename:
                return True
        return False

    def _log_filter_error(self, query, level, exc):
        """Report a filtering parsing error in the logging"""
        filter = getattr(query, "filter", None)  # AdhocQuery only
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

    def _get_locator(self, **params):
        """Tell which field is likely causing the query error"""
        if params["resourceID"]:
            return "resourceId"
        elif params["STOREDQUERY_ID"]:
            return "STOREDQUERY_ID"
        else:
            return "filter"


class GetFeature(BaseWFSGetDataMethod):
    """This returns all properties of the feature.

    Various query parameters allow limiting the data.
    """

    output_formats = [
        OutputFormat(
            # Needed for cite compliance tests
            "application/gml+xml",
            version="3.2",
            renderer_class=output.gml32_renderer,
        ),
        OutputFormat(
            "text/xml", subtype="gml/3.2.1", renderer_class=output.gml32_renderer
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


class GetPropertyValue(BaseWFSGetDataMethod):
    """This returns a limited set of properties of the feature.
    It works almost identical to GetFeature, except that it returns a single field.
    """

    output_formats = [
        OutputFormat(
            "text/xml", subtype="gml/3.2", renderer_class=output.gml32_value_renderer
        ),
    ]

    parameters = BaseWFSGetDataMethod.parameters + [
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
