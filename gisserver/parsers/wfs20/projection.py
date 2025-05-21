"""Projection tag parsing for WFS 2.0"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gisserver.exceptions import (
    InvalidParameterValue,
    OperationParsingFailed,
    OperationProcessingFailed,
)
from gisserver.parsers.ast import AstNode, tag_registry
from gisserver.parsers.query import CompiledQuery
from gisserver.parsers.xml import NSElement, xmlns
from gisserver.types import XPathMatch


class ResolveValue(Enum):
    """The ``wfs:ResolveValueType`` enum, used by :class:`StandardResolveParameters`."""

    local = "local"
    remote = "remote"
    all = "all"
    none = "none"

    @classmethod
    def _missing_(cls, value):
        raise OperationParsingFailed(f"Invalid resolve value: {value}", locator="resolve")


@dataclass
@tag_registry.register("PropertyName", xmlns.wfs)
class PropertyName(AstNode):
    """The ``<wfs:PropertyName>`` element in the projection clause.

    This parses and handles the syntax::

        <wfs:PropertyName>ns0:tagname</wfs:PropertyName>

    More advanced syntax is not supported, such as::

      <wfs:PropertyName resolve="all" resolvePath="valueOf(relatedTo)">valueOf(registerEntry)</wfs:PropertyName>

    Note this element exists in the WFS namespace, not the FES namespace!
    The ``<fes:PropertyName>`` is an old FES 1.x element that has been replaced by ``<fes:ValueReference>``.
    The old ``<fes:PropertyName>`` is still supported as an alias by this server.
    """

    xpath: str  # Officially only a 'QName'
    xpath_ns_aliases: dict[str, str]

    # Unused, yet included for completeness.
    # These are available in the XML syntax, and override
    # the default given in the <wfs:GetFeature> element.
    resolve: ResolveValue = ResolveValue.none
    resolve_depth: int | None = None
    resolve_path: str | None = None
    resolve_timeout: int = 300

    @classmethod
    def from_xml(cls, element: NSElement):
        """Parse the XML tag."""
        depth = parse_resolve_depth(element.attrib.get("resolveDepth", None))
        return cls(
            xpath=element.text,
            resolve=ResolveValue[element.attrib.get("resolve", "none")],
            resolve_depth=depth,
            resolve_path=element.attrib.get("resolvePath"),
            resolve_timeout=element.get_int_attribute("resolveTimeout", 300),
            xpath_ns_aliases=element.ns_aliases,
        )

    def parse_xpath(self, feature_types: list) -> XPathMatch:
        """Convert the XPath into the required ORM query elements."""
        if self.resolve_path:
            raise OperationProcessingFailed("resolvePath is not supported", locator="propertyName")
        if "valueOf(" in self.xpath or (self.resolve_path and "valueOf(" in self.resolve_path):
            raise OperationProcessingFailed(
                "valueOf(..) syntax is not supported", locator="propertyName"
            )

        # Can resolve against XSD paths, find the correct DB field name
        return feature_types[0].resolve_element(self.xpath, self.xpath_ns_aliases)

    def decorate_query(self, compiler: CompiledQuery):
        """Update the low-level query based on this property projection."""
        # This will also validate the name because it resolves the ORM path.
        # The actual limiting of fields happens inside the decorate_queryset() of the renderer.
        xpath_match = self.parse_xpath(compiler.feature_types)
        if xpath_match.orm_filters:
            # Apply any xpath [attr=value] lookups.
            compiler.add_extra_lookup(xpath_match.orm_filters)


def parse_resolve_depth(depth: str | None) -> int | None:
    """Parse the resolve depth value."""
    try:
        return None if depth is None or depth == "*" else int(depth)
    except (ValueError, TypeError) as e:
        raise InvalidParameterValue(
            "ResolveDepth must be an integer or '*'", locator="resolveDepth"
        ) from e
