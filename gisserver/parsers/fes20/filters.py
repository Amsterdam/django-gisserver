from dataclasses import dataclass
from typing import List, Union
from xml.etree.ElementTree import Element, QName

from gisserver.parsers.base import FES20, tag_registry
from gisserver.parsers.utils import expect_tag
from . import expressions, identifiers, operators

FilterPredicates = Union[expressions.Function, List[identifiers.Id], operators.Operator]


@dataclass
class Filter:
    """The <fes20:Filter> element."""

    predicate: FilterPredicates

    @classmethod
    @expect_tag(FES20, "Filter")
    def from_xml(cls, element: Element) -> "Filter":
        """Parse the <fes20:Filter> element."""
        if len(element) > 1 or element[0].tag == QName(FES20, "ResourceId"):
            # fes20:ResourceId is the only element that may appear multiple times.
            return Filter(
                predicate=[identifiers.Id.from_child_xml(child) for child in element]
            )
        else:
            return Filter(
                predicate=tag_registry.from_child_xml(
                    element[0], allowed_types=(expressions.Function, operators.Operator)
                )
            )
