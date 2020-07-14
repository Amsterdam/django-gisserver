from dataclasses import dataclass
from enum import Enum
from typing import List

from gisserver.exceptions import InvalidParameterValue
from gisserver.parsers.fes20 import ValueReference


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
                "sortby", "Expect ASC/DESC ordering direction"
            ) from None


@dataclass
class SortProperty:
    """This class name is based on the WFS spec."""

    value_reference: ValueReference
    sort_order: SortOrder = SortOrder.ASC


@dataclass
class SortBy:
    """The sortBy clause."""

    sort_properties: List[SortProperty]

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

    def build_ordering(self, feature_type=None) -> List[str]:
        """Build the ordering for the Django ORM call."""
        ordering = []
        for prop in self.sort_properties:
            if feature_type is not None:
                orm_path = prop.value_reference.parse_xpath(feature_type).orm_path
            else:
                orm_path = prop.value_reference.xpath.replace("/", "__")

            ordering.append(f"{prop.sort_order.value}{orm_path}")
        return ordering
