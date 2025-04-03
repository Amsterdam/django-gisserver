from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gisserver.exceptions import InvalidParameterValue
from gisserver.parsers.fes20 import ValueReference
from gisserver.parsers.query import CompiledQuery
from gisserver.parsers.xml import NSElement, split_ns, xmlns

FES_SORT_ORDER = xmlns.fes20.qname("SortOrder")


class SortOrder(Enum):
    ASC = ""
    DESC = "-"

    # Support WFS 1 names for clients that still use this.
    A = ASC
    D = DESC

    @classmethod
    def from_string(cls, direction):
        try:
            return cls[direction]
        except KeyError:
            raise InvalidParameterValue(
                "Expect ASC/DESC ordering direction", locator="sortby"
            ) from None


@dataclass
class SortProperty:
    """This class name is based on the WFS spec."""

    value_reference: ValueReference
    sort_order: SortOrder = SortOrder.ASC


@dataclass
class SortBy:
    """The sortBy clause."""

    sort_properties: list[SortProperty]

    @classmethod
    def from_any(cls, value: str | NSElement):
        if isinstance(value, NSElement):
            return cls.from_xml(value)
        else:
            return cls.from_string(value)

    @classmethod
    def from_string(cls, value: str):
        """Construct the SortBy object from a KVP "SORTBY" parameter."""
        props = []
        for field in value.split(","):
            if "[" in field:
                raise InvalidParameterValue(
                    "sortby", "Sorting with XPath attribute selectors is not supported."
                )

            if " " in field:
                xpath, direction = field.split(" ", 1)
                props.append(
                    SortProperty(
                        value_reference=ValueReference(xpath),
                        sort_order=SortOrder.from_string(direction),
                    )
                )
            else:
                props.append(SortProperty(value_reference=ValueReference(field)))

        return cls(sort_properties=props)

    @classmethod
    def from_xml(cls, element: NSElement):
        props = []
        ns, _tag = split_ns(element.tag)
        for prop in element:
            sort_order = prop.find(FES_SORT_ORDER)
            sort_property = SortProperty(
                value_reference=ValueReference.from_xml(prop[0]),
                sort_order=(
                    SortOrder.from_string(sort_order.text)
                    if sort_order is not None
                    else SortOrder.ASC
                ),
            )
            props.append(sort_property)
        return cls(sort_properties=props)

    def build_ordering(self, compiler: CompiledQuery):
        """Build the ordering for the Django ORM call."""
        ordering = []
        for prop in self.sort_properties:
            if compiler.feature_type is not None:
                orm_path = prop.value_reference.parse_xpath(compiler.feature_type).orm_path
            else:
                orm_path = prop.value_reference.xpath.replace("/", "__")

            ordering.append(f"{prop.sort_order.value}{orm_path}")

        compiler.add_ordering(ordering)
