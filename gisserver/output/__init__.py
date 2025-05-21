"""The output rendering classes for all response types.

This also includes collection classes for iterating over the Django QuerySet results.
"""

from .results import FeatureCollection, SimpleFeatureCollection  # isort: skip (fixes import loops)

from .base import CollectionOutputRenderer, OutputRenderer, XmlOutputRenderer
from .csv import CSVRenderer, DBCSVRenderer
from .geojson import DBGeoJsonRenderer, GeoJsonRenderer
from .gml32 import (
    DBGML32Renderer,
    DBGML32ValueRenderer,
    GML32Renderer,
    GML32ValueRenderer,
)
from .stored import DescribeStoredQueriesRenderer, ListStoredQueriesRenderer
from .utils import to_qname
from .xmlschema import XmlSchemaRenderer

__all__ = [
    "OutputRenderer",
    "CollectionOutputRenderer",
    "FeatureCollection",
    "SimpleFeatureCollection",
    "DBCSVRenderer",
    "DBGeoJsonRenderer",
    "DBGML32Renderer",
    "DBGML32ValueRenderer",
    "CSVRenderer",
    "GeoJsonRenderer",
    "GML32Renderer",
    "GML32ValueRenderer",
    "XmlOutputRenderer",
    "XmlSchemaRenderer",
    "ListStoredQueriesRenderer",
    "DescribeStoredQueriesRenderer",
    "to_qname",
]
