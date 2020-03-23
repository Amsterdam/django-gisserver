"""All parser logic to process <fes:...> and <gml:...> tags."""

from .base import FES20 as FES20_NS
from .fes20 import Filter
from .gml import parse_gml, GML21 as GML21_NS, GML32 as GML32_NS
from .queries import AdhocQuery

parse_fes = Filter.from_string

__all__ = [
    "AdhocQuery",
    "parse_fes",
    "parse_gml",
    "FES20_NS",
    "GML21_NS",
    "GML32_NS",
]
