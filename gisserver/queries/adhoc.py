"""Handle adhoc-query objects.

The adhoc query is based on incoming request parameters,
such as the "FILTER", "BBOX" and "RESOURCEID" parameters.

These definitions follow the WFS spec.
"""
import logging
from dataclasses import dataclass

from django.db.models import Q
from typing import List, Optional

from gisserver import conf
from gisserver.exceptions import (
    InvalidParameterValue,
    MissingParameterValue,
)
from gisserver.features import FeatureType
from gisserver.geometries import BoundingBox
from gisserver.parsers import fes20
from gisserver.parsers.fes20 import operators
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
    sortBy: Optional[fes20.SortBy] = None

    # Officially part of the GetFeature/GetPropertyValue request object,
    # but included here for ease of query implementation.
    resourceId: Optional[fes20.IdOperator] = None

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
                id_type_names = params["resourceID"].type_names
                if id_type_names:
                    # Only test when the RESOURCEID has a typename.id format
                    # Otherwise, this breaks the CITE RESOURCEID=test-UUID parameter.
                    kvp_type_names = {
                        feature_type.name for feature_type in params["typeNames"]
                    }
                    if not kvp_type_names.issuperset(id_type_names):
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
            feature_types = [
                self.resolve_type_name(type_name, locator="resourceID")
                for type_name in self.resourceId.type_names
            ]

            # Also make the behavior consistent, always supply the type name.
            if not self.typeNames:
                self.typeNames = feature_types

    def get_type_names(self):
        return self.typeNames

    def compile_query(
        self, feature_type: FeatureType, using=None
    ) -> fes20.CompiledQuery:
        """Return our internal CompiledQuery object that can be applied to the queryset."""
        if self.filter:
            # Generate the internal query object from the <fes:Filter>
            return self.filter.compile_query(feature_type, using=using)
        else:
            # Generate the internal query object from the BBOX and sortBy args.
            return self._compile_non_filter_query(feature_type, using=using)

    def _compile_non_filter_query(self, feature_type, using=None):
        """Generate the query based on the remaining parameters.

        This is slightly more efficient then generating the fes Filter object
        from these KVP parameters (which could also be done within the request method).
        """
        compiler = fes20.CompiledQuery(feature_type=feature_type, using=using)

        if self.bbox:
            # Validate whether the provided SRID is supported.
            # While PostGIS would support many more ID's,
            # it would crash when an unsupported ID is given.
            crs = self.bbox.crs
            if (
                conf.GISSERVER_SUPPORTED_CRS_ONLY
                and crs is not None
                and crs not in feature_type.supported_crs
            ):
                raise InvalidParameterValue(
                    "bbox",
                    f"Feature '{feature_type.name}' does not support SRID {crs.srid}.",
                )

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
