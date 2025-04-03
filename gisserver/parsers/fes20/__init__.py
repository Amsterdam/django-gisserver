from __future__ import annotations

from gisserver.exceptions import OperationParsingFailed

from . import lookups  # noqa: F401 (need to register ORM lookups)
from .expressions import ValueReference
from .filters import Filter
from .functions import function_registry
from .identifiers import ResourceId
from .operators import IdOperator
from .sorting import SortBy

__all__ = [
    "Filter",
    "ValueReference",
    "ResourceId",
    "IdOperator",
    "SortBy",
    "function_registry",
]


def parse_resource_id_kvp(value) -> IdOperator:
    """Parse the RESOURCEID parameter.
    This returns an IdOperator, as it needs to support multiple pairs.
    """
    return IdOperator([ResourceId(rid) for rid in value.split(",")])


def parse_property_name(value) -> list[ValueReference] | None:
    """Parse the PROPERTYNAME parameter"""
    if not value or value == "*":
        return None  # WFS 1 logic

    if "(" in value:
        raise OperationParsingFailed(
            "Parameter lists to perform multiple queries are not supported yet.",
            locator="propertyname",
        )

    return [ValueReference(x) for x in value.split(",")]
