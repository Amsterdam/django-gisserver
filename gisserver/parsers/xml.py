"""XML parsing for all incoming requests.

This logic uses the etree logic from the standard library,
with some extra extensions to expose the original namespace aliases.
Using defusedxml, incoming DOS attacks are prevented.

To handle more complex XML structures, consider building an Abstract Syntax Tree (AST)
to translate the XML Element classes into Python objects.
The :mod:`gisserver.parsers.ast` module provides the building blocks for that.
"""

from __future__ import annotations

from enum import Enum
from xml.etree.ElementTree import Element, QName, TreeBuilder

from defusedxml.ElementTree import DefusedXMLParser, ParseError

from gisserver.exceptions import ExternalParsingError

__all__ = (
    "xmlns",
    "NSElement",
    "parse_xml_from_string",
    "get_attribute",
    "get_child",
)


class xmlns(Enum):
    """Common namespaces within WFS land.
    Note these short aliases are arbitrary in XML syntax; the XML code may use any alias (such as ns0).
    The full qualified name (e.g. ``<{http://www.opengis.net/gml/3.2}Point>``) is the actual tag name.
    """

    xml = "http://www.w3.org/XML/1998/namespace"
    xsd = "http://www.w3.org/2001/XMLSchema"
    xsi = "http://www.w3.org/2001/XMLSchema-instance"
    ows = "http://www.opengis.net/ows/1.1"
    wfs = "http://www.opengis.net/wfs/2.0"
    fes20 = "http://www.opengis.net/fes/2.0"
    gml21 = "http://www.opengis.net/gml"
    gml32 = "http://www.opengis.net/gml/3.2"
    xlink = "http://www.w3.org/1999/xlink"
    gml = gml32  # alias

    def __str__(self):
        # Python 3.11+ has StrEnum for this.
        return self.value

    def qname(self, local_name) -> str:
        """Convert the tag name into a fully qualified name."""
        return QName(self.value, local_name).text


class NSElement(Element):
    """Custom XML element, which also exposes its original namespace aliases.
    That information is needed to parse text content and attributes in WFS.
    For example:
    * ``<ValueReference>ns0:elementName</ValueReference>``
    * ``<Query typeNames="ns1:name">``
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ns_aliases = {}


class NSTreeBuilder(TreeBuilder):
    """Custom TreeBuilder to track namespaces."""

    def __init__(self, **kwargs):
        super().__init__(element_factory=NSElement, **kwargs)
        self.ns_stack = [{}]

    def start(self, tag, attrs):
        super().start(tag, attrs)
        self.ns_stack.append({})

    def start_ns(self, prefix, uri):
        self.ns_stack[-1][prefix] = uri

    def end(self, tag) -> Element:
        element = super().end(tag)
        element.ns_aliases = self._flatten_ns()
        self.ns_stack.pop()
        return element

    def _flatten_ns(self) -> dict:
        result = {}
        for level in self.ns_stack:
            result.update(level)
        return result


def parse_xml_from_string(xml_string: str | bytes) -> NSElement:
    """Provide a safe and consistent way for parsing XML.

    This uses a custom parser, so namespace aliases can be tracked.
    All elements also have an :attr:`ns_aliases` attribute that exposes
    the original alias that was used for the namespace.
    """
    # Passing a custom parser potentially circumvents defusedxml,
    # so note the parser is again configured in the same way:
    parser = DefusedXMLParser(
        target=NSTreeBuilder(),
        forbid_dtd=True,
        forbid_entities=True,
        forbid_external=True,
    )

    try:
        parser.feed(xml_string)
        return parser.close()
    except ParseError as e:
        # Offer consistent results for callers to check for invalid data.
        raise ExternalParsingError(str(e)) from e


def get_child(root: NSElement, namespace: xmlns | str, localname: str) -> NSElement | None:
    """Find the element using a fully qualified name."""
    return root.find(QName(namespace, localname).text)


def get_attribute(element: NSElement, name: str) -> str:
    """Resolve an attribute, raise an error when it's missing."""
    try:
        return element.attrib[name]
    except KeyError:
        raise ExternalParsingError(
            f"Element {element.tag} misses required attribute '{name}'"
        ) from None
