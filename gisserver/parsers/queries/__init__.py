"""Entry point to handle queries.

WFS defines 2 query types:
- Adhoc queries are constructed directly from request parameters.
- Stored queries are defined first, and executed later.

Both use the FES (Filter Encoding Syntax) filtering logic internally.

The objects in this module closely follow the WFS spec.
By using the same type definitions, a lot of code logic follows naturally.
The "GetFeatureById" is a mandatory built-in stored query.
"""
from .base import QueryExpression
from .adhoc import AdhocQuery
from .stored import (
    QueryExpressionText,
    StoredQueryDescription,
    StoredQuery,
    stored_query_registry,
    StoredQueryParameter,
    GetFeatureById,
)

__all__ = (
    "QueryExpression",
    "AdhocQuery",
    "QueryExpressionText",
    "StoredQueryDescription",
    "StoredQuery",
    "stored_query_registry",
    "StoredQueryParameter",
    "GetFeatureById",
)
