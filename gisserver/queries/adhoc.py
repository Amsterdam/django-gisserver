"""Handle adhoc-query objects.

The adhoc query is based on incoming request parameters,
such as the "FILTER", "BBOX" and "RESOURCEID" parameters.

These definitions follow the WFS spec.
"""
import logging
from dataclasses import dataclass

from django.core.exceptions import FieldError
from django.db import ProgrammingError
from django.db.models import Q
from typing import List, Optional

from gisserver import output
from gisserver.exceptions import (
    InvalidParameterValue,
    MissingParameterValue,
)
from gisserver.features import FeatureType
from gisserver.geometries import BoundingBox
from gisserver.parsers import fes20
from gisserver.parsers.fes20 import ResourceId, operators
from .base import QueryExpression

logger = logging.getLogger(__name__)


@dataclass
class AdhocQuery(QueryExpression):
    """The Ad hoc query expression parameters.

    This represents all dynamic queries received as request (hence "adhoc"),
    such as the "FILTER" and "BBOX" arguments from a HTTP GET.

    The WFS Spec has 3 class levels for this:
    - AdhocQueryExpression (types, projection, selection, sorting)
    - Query (adds srsName, featureVersion)

    For KVP requests, this dataclass is almost identical to **params.
    However, it allows combining the filter parameters. These become
    one single XML request for HTTP POST requests later.
    """

    typeNames: List[FeatureType]  # typeNames in WFS/FES spec
    # aliases: Optional[List[str]] = None
    handle: str = ""  # only for XML POST requests

    # Projection clause:
    # propertyName

    # Selection clause:
    # - for XML POST this is encoded in a <fes:Query>
    # - for HTTP GET, this is encoded as FILTER, FILTER_LANGUAGE, RESOURCEID, BBOX.
    filter: Optional[fes20.Filter] = None
    filter_language: str = fes20.Filter.query_language
    bbox: Optional[BoundingBox] = None

    # Sorting Clause
    sortBy: Optional[List[str]] = None

    # Officially part of the GetFeature/GetPropertyValue request object,
    # but included here for ease of query implementation.
    resourceId: Optional[ResourceId] = None

    # GetPropertyValue:
    # In the WFS spec, this is only part of the operation/presentation.
    # For Django, we'd like to make this part of the query too.
    value_reference: Optional[fes20.ValueReference] = None

    @classmethod
    def from_kvp_request(cls, **params):
        """Build this object from a HTTP GET (key-value-pair) request."""
        # Validate optionally required parameters
        if not params["typeNames"] and not params["resourceID"]:
            raise MissingParameterValue("typeNames", "Empty TYPENAMES parameter")

        # Validate mutually exclusive parameters
        if params["filter"] and (params["bbox"] or params["resourceID"]):
            raise InvalidParameterValue(
                "filter",
                "The FILTER parameter is mutually exclusive with BBOX and RESOURCEID",
            )

        # Validate mutually exclusive parameters
        if params["resourceID"]:
            if params["bbox"] or params["filter"]:
                raise InvalidParameterValue(
                    "resourceID",
                    "The RESOURCEID parameter is mutually exclusive with BBOX and FILTER",
                )

            # When ResourceId + typenames is defined, it should be a value from typenames
            # see WFS spec 7.9.2.4.1
            if params["typeNames"]:
                raw_type_names = [
                    feature_type.name for feature_type in params["typeNames"]
                ]
                if params["resourceID"].type_name not in raw_type_names:
                    raise InvalidParameterValue(
                        "resourceID",
                        "When TYPENAMES and RESOURCEID are combined, "
                        "the RESOURCEID type should be included in TYPENAMES.",
                    )

        return AdhocQuery(
            typeNames=params["typeNames"],
            filter=params["filter"],
            filter_language=params["filter_language"],
            bbox=params["bbox"],
            sortBy=params["sortBy"],
            resourceId=params["resourceID"],
            value_reference=params.get("valueReference"),
        )

    def bind(self, *args, **kwargs):
        """Inform this quey object of the available feature types"""
        super().bind(*args, **kwargs)

        if self.resourceId:
            # Early validation whether the selected resourceID type exists.
            feature_type = self.resolve_type_name(
                self.resourceId.type_name, locator="resourceID"
            )

            # Also make the behavior consistent, always supply the type name.
            if not self.typeNames:
                self.typeNames = [feature_type]

    def get_results(self, start_index=0, count=100) -> output.FeatureCollection:
        """Overwritten to improve error handling messages."""
        try:
            return super().get_results(start_index=start_index, count=count)
        except ProgrammingError as e:
            # e.g. comparing datetime against integer
            self._log_filter_error(logging.WARNING, e)
            raise InvalidParameterValue(
                self._get_locator(),
                "Invalid filter query, check the used datatypes and field names.",
            ) from e

    def get_type_names(self):
        return self.typeNames

    def get_queryset(self, feature_type: FeatureType):
        """Overwritten to improve error handling messages."""
        try:
            return super().get_queryset(feature_type)
        except FieldError as e:
            # e.g. doing a LIKE on a foreign key, or requesting an unknown field.
            self._log_filter_error(logging.ERROR, e)
            raise InvalidParameterValue(
                self._get_locator(), f"Internal error when processing filter",
            ) from e
        except (ValueError, TypeError) as e:
            raise InvalidParameterValue(
                self._get_locator(), f"Invalid filter query: {e}",
            ) from e

    def _log_filter_error(self, level, exc):
        """Report a filtering parsing error in the logging"""
        fes_xml = self.filter.source if self.filter is not None else "(not provided)"
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

    def _get_locator(self):
        """Tell which field is likely causing the query error"""
        if self.resourceId:
            return "resourceId"
        else:
            return "filter"

    def compile_query(self, feature_type: FeatureType) -> fes20.CompiledQuery:
        """Return our internal CompiledQuery object that can be applied to the queryset."""
        if self.filter:
            # Generate the internal query object from the <fes:Filter>
            return self.filter.compile_query(feature_type)
        else:
            # Generate the internal query object from the BBOX and sortBy args.
            return self._compile_non_filter_query(feature_type)

    def _compile_non_filter_query(self, feature_type):
        """Generate the query based on the remaining parameters.

        This is slightly more efficient then generating the fes Filter object
        from these KVP parameters (which could also be done within the request method).
        """
        compiler = fes20.CompiledQuery(feature_type=feature_type)

        if self.bbox:
            # Using __within does not work with geometries
            # that only partially exist within the bbox
            lookup = operators.SpatialOperatorName.BBOX.value  # "intersects"
            filters = {
                f"{feature_type.geometry_field_name}__{lookup}": self.bbox.as_polygon(),
            }
            compiler.add_lookups(Q(**filters))

        if self.resourceId:
            self.resourceId.build_query(compiler=compiler)

        if self.sortBy:
            compiler.add_sort_by(self.sortBy)

        return compiler
