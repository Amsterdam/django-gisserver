"""WFS 2.0 element parsing.

These classes parse the XML request body.

The full spec can be found at: https://www.ogc.org/publications/standard/wfs/.
Secondly, using https://www.mediamaps.ch/ogc/schemas-xsdoc/sld/1.2/wfs_xsd.html can be very
helpful to see which options each object type should support.
"""

from .adhoc import AdhocQuery
from .base import QueryExpression
from .projection import PropertyName
from .requests import (
    DescribeFeatureType,
    DescribeStoredQueries,
    GetCapabilities,
    GetFeature,
    GetPropertyValue,
    ListStoredQueries,
    ResultType,
)
from .stored import StoredQuery

__all__ = (
    # Requests
    "GetCapabilities",
    "DescribeFeatureType",
    "GetFeature",
    "GetPropertyValue",
    "ListStoredQueries",
    "DescribeStoredQueries",
    "ResultType",
    # Queries
    "QueryExpression",
    "AdhocQuery",
    "StoredQuery",
    # Projection
    "PropertyName",
)
