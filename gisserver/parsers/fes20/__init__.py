from .expressions import ValueReference
from .filters import Filter
from .functions import function_registry
from .identifiers import ResourceId
from .operators import IdOperator
from .query import CompiledQuery
from .sorting import SortBy

__all__ = [
    "Filter",
    "CompiledQuery",
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
