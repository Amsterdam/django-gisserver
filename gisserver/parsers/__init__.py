"""All parser logic to process <fes:...> and <gml:...> tags."""

from .fes20 import Filter, function_registry as fes_function_registry
from .gml import parse_gml

parse_fes = Filter.from_string

__all__ = [
    "parse_fes",
    "parse_gml",
    "fes_function_registry",
]
