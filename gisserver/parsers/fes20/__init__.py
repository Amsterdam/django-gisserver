"""Parsing and processing of the OGC Filter Encoding Standard 2.0 (FES).

This parses the XML syntax, and translates that into a Django ORM query.

It's also possible to register custom functions,
which will include Django ORM function as part of the filter language.

The full spec can be found at: https://www.ogc.org/publications/standard/filter/.
Secondly, using https://www.mediamaps.ch/ogc/schemas-xsdoc/sld/1.2/filter_xsd.html
can be very helpful to see which options each object type should support.
"""

from __future__ import annotations

from . import lookups  # noqa: F401 (need to register ORM lookups)
from .expressions import (
    BinaryOperator,
    BinaryOperatorType,
    Expression,
    Function,
    Literal,
    ValueReference,
)
from .filters import Filter
from .identifiers import Id, ResourceId, VersionActionTokens
from .operators import (
    BetweenComparisonOperator,
    BinaryComparisonName,
    BinaryComparisonOperator,
    BinaryLogicOperator,
    BinaryLogicType,
    BinarySpatialOperator,
    ComparisonOperator,
    DistanceOperator,
    DistanceOperatorName,
    ExtensionOperator,
    IdOperator,
    LikeOperator,
    LogicalOperator,
    MatchAction,
    Measure,
    NilOperator,
    NonIdOperator,
    NullOperator,
    Operator,
    SpatialOperator,
    SpatialOperatorName,
    TemporalOperator,
    TemporalOperatorName,
    UnaryLogicOperator,
    UnaryLogicType,
)
from .sorting import SortBy, SortOrder, SortProperty

__all__ = [
    "Filter",
    # Expressions
    "Expression",
    "Function",
    "Literal",
    "ValueReference",
    # WFS 1.0 expressions
    "BinaryOperator",
    "BinaryOperatorType",
    # Identifiers
    "Id",
    "ResourceId",
    "VersionActionTokens",
    # Operators
    "BetweenComparisonOperator",
    "BinaryComparisonName",
    "BinaryComparisonOperator",
    "BinaryLogicOperator",
    "BinaryLogicType",
    "BinarySpatialOperator",
    "ComparisonOperator",
    "DistanceOperator",
    "DistanceOperatorName",
    "ExtensionOperator",
    "IdOperator",
    "LikeOperator",
    "LogicalOperator",
    "MatchAction",
    "Measure",
    "NilOperator",
    "NonIdOperator",
    "NullOperator",
    "Operator",
    "SpatialOperator",
    "SpatialOperatorName",
    "TemporalOperator",
    "TemporalOperatorName",
    "UnaryLogicOperator",
    "UnaryLogicType",
    # Sorting
    "SortBy",
    "SortOrder",
    "SortProperty",
    "SortBy",
]
