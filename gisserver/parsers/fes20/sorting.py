from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gisserver.exceptions import InvalidParameterValue
from gisserver.parsers.fes20 import ValueReference
from gisserver.parsers.xml import NSElement, get_child, split_ns


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
    def from_xml(cls, elem: NSElement):
        props = []
        ns, _tag = split_ns(elem.tag)
        for prop in elem:
            valueref = get_child(prop, ns, "ValueReference")
            sort_order = get_child(prop, ns, "SortOrder")
            sort_property = SortProperty(
                value_reference=ValueReference(valueref.text),
                sort_order=(
                    SortOrder.from_string(sort_order.text)
                    if sort_order is not None
                    else SortOrder.ASC
                ),
            )
            props.append(sort_property)
        return cls(sort_properties=props)

    def build_ordering(self, feature_type=None) -> list[str]:
        """Build the ordering for the Django ORM call."""
        ordering = []
        for prop in self.sort_properties:
            if feature_type is not None:
                orm_path = prop.value_reference.parse_xpath(feature_type).orm_path
            else:
                orm_path = prop.value_reference.xpath.replace("/", "__")

            ordering.append(f"{prop.sort_order.value}{orm_path}")
        return ordering
