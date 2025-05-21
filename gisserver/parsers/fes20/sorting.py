"""The FES elements that handle sorting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gisserver.exceptions import InvalidParameterValue
from gisserver.parsers.ast import AstNode, expect_children, expect_tag, tag_registry
from gisserver.parsers.fes20 import ValueReference
from gisserver.parsers.ows import KVPRequest
from gisserver.parsers.query import CompiledQuery
from gisserver.parsers.xml import NSElement, xmlns

FES_SORT_ORDER = xmlns.fes20.qname("SortOrder")


class SortOrder(Enum):
    #: Ascending order
    ASC = ""
    #: Descrending order
    DESC = "-"

    # Support WFS 1 names for clients that still use this:

    #: WFS 1 name that clients still use for ascending.
    A = ASC
    #: WFS 1 name that clients still use for descending.
    D = DESC

    @classmethod
    def from_string(cls, direction):
        try:
            return cls[direction]
        except KeyError:
            raise InvalidParameterValue(
                "Expect ASC/DESC ordering direction", locator="sortby"
            ) from None

    @classmethod
    @expect_tag(xmlns.fes20, "SortOrder")
    def from_xml(cls, element: NSElement):
        return SortOrder.from_string(element.text)


@dataclass
@tag_registry.register("SortProperty", xmlns.fes20)
class SortProperty(AstNode):
    """This class name is based on the WFS spec.

    This parses and handles the syntax::

        <fes:SortProperty>
            <fes:ValueReference>name</fes:ValueReference>
            <fes:SortOrder>ASC</fes:SortOrder>
        </fes:SortProperty>
    """

    value_reference: ValueReference
    sort_order: SortOrder = SortOrder.ASC

    def __post_init__(self):
        if "[" in self.value_reference.xpath:
            raise InvalidParameterValue(
                "Sorting with XPath attribute selectors is not supported.", locator="sortby"
            )

    @classmethod
    @expect_tag(xmlns.fes20, "SortProperty")
    @expect_children(1, ValueReference, FES_SORT_ORDER)
    def from_xml(cls, element: NSElement) -> SortProperty:
        """Parse the incoming XML"""
        sort_order = element.find(FES_SORT_ORDER)
        return cls(
            value_reference=ValueReference.from_xml(element[0]),
            sort_order=(
                SortOrder.from_xml(sort_order) if sort_order is not None else SortOrder.ASC
            ),
        )

    @classmethod
    def from_string(cls, value: str, ns_aliases: dict[str, str]) -> SortProperty:
        """Parse the incoming GET parameter."""
        xpath, _, direction = value.partition(" ")
        return SortProperty(
            value_reference=ValueReference(xpath, ns_aliases),
            sort_order=SortOrder.from_string(direction) if direction else SortOrder.ASC,
        )

    def as_kvp(self):
        """Translate the POST request into KVP GET parameters. This is needed for pagination."""
        if self.sort_order == SortOrder.ASC:
            return self.value_reference.xpath
        else:
            return f"{self.value_reference.xpath} {self.sort_order.name}"


@dataclass
@tag_registry.register("SortBy", xmlns.fes20)
class SortBy(AstNode):
    """The sortBy clause.

    This parses and handles the syntax::

        <fes:SortBy>
            <fes:SortProperty>
                <fes:ValueReference>name</fes:ValueReference>
                <fes:SortOrder>ASC</fes:SortOrder>
            </fes:SortProperty>
        </fes:SortBy>

    It also supports the SORTBY parameter for GET requests.
    """

    #: The ``<fes:SortProperty>`` elements.
    sort_properties: list[SortProperty]

    @classmethod
    @expect_children(1, SortProperty)
    def from_xml(cls, element: NSElement) -> SortBy:
        """Parse the XML tag."""
        return cls(
            sort_properties=[
                # The from_xml() validates that the child node is a <fes:SortProperty>
                SortProperty.from_xml(child)
                for child in element
            ]
        )

    @classmethod
    def from_kvp_request(cls, kvp: KVPRequest) -> SortBy | None:
        """Construct the SortBy object from a KVP "SORTBY" parameter, and considering NAMESPACES."""
        value = kvp.get_str("SortBy", default=None)
        if value is None:
            return None

        return cls(
            sort_properties=[
                SortProperty.from_string(field, kvp.ns_aliases) for field in value.split(",")
            ]
        )

    def as_kvp(self) -> str:
        """Translate the POST request into KVP GET parameters. This is needed for pagination."""
        return ",".join(sort_property.as_kvp() for sort_property in self.sort_properties)

    def build_ordering(self, compiler: CompiledQuery):
        """Build the ordering for the Django ORM call."""
        ordering = []
        for prop in self.sort_properties:
            orm_path = prop.value_reference.parse_xpath(compiler.feature_types).orm_path
            ordering.append(f"{prop.sort_order.value}{orm_path}")

        compiler.add_ordering(ordering)
