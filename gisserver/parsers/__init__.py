"""All parser logic to process <fes:...> and <gml:...> tags."""

from .base import FES20 as FES20_NS
from .fes20 import parse_fes
from .gml import parse_gml, GML21 as GML21_NS, GML32 as GML32_NS


__all__ = [
    "parse_fes",
    "parse_gml",
    "FES20_NS",
    "GML21_NS",
    "GML32_NS",
]
