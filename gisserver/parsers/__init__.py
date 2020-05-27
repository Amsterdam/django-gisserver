"""All parser logic to process <fes:...> and <gml:...> tags."""

from .base import FES20 as FES20_NS
from .fes20 import Filter, function_registry as fes_function_registry
from .gml import parse_gml, GML21 as GML21_NS, GML32 as GML32_NS

parse_fes = Filter.from_string

__all__ = [
    "parse_fes",
    "parse_gml",
    "fes_function_registry",
    "FES20_NS",
    "GML21_NS",
    "GML32_NS",
]
