"""Handle query objects"""
from dataclasses import dataclass
from typing import List, Optional

from django.db.models import Q

from gisserver.exceptions import InvalidParameterValue
from gisserver.features import FeatureType
from gisserver.parsers import fes20
from gisserver.parsers.fes20 import operators
from gisserver.types import BoundingBox


class QueryExpression:
    """WFS base class for all queries."""

    handle = ""

    def get_fes_query(self, feature_type: FeatureType) -> fes20.FesQuery:
        """Generate the FES query."""
        raise NotImplementedError()


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

    @classmethod
    def from_kvp_request(cls, **params):
        """Build this object from a HTTP GET (key-value-pair) request."""
        # Allow filtering using a <fes:Filter>
        if params["filter"] and (params["bbox"] or params["resourceID"]):
            raise InvalidParameterValue(
                "filter",
                "The FILTER parameter is mutually exclusive with BBOX and RESOURCEID",
            )

        return AdhocQuery(
            typeNames=params["typeNames"],
            filter=params["filter"],
            filter_language=params["filter_language"],
            bbox=params["bbox"],
            sortBy=params["sortBy"],
        )

    def get_fes_query(self, feature_type: FeatureType) -> fes20.FesQuery:
        """Return our internal FesQuery object that can be applied to the queryset."""
        if self.filter:
            return self.filter.get_query()

        query = fes20.FesQuery()
        # Allow filtering within a bounding box
        if self.bbox:
            # Using __within does not work with geometries
            # that only partially exist within the bbox
            lookup = operators.SpatialOperatorName.BBOX.value  # "intersects"
            filters = {
                f"{feature_type.geometry_field_name}__{lookup}": self.bbox.as_polygon(),
            }
            query.add_lookups(Q(**filters))

        if self.sortBy:
            query.add_sort_by(self.sortBy)

        return query
