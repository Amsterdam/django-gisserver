"""XML parsing for all incoming requests.

This logic uses the etree logic from the standard library,
with some extra extensions to expose the original namespace aliases.
Using defusedxml, incoming DOS attacks are prevented.

To handle more complex XML structures, consider building an Abstract Syntax Tree (AST)
to translate the XML Element classes into Python objects.
The :mod:`gisserver.parsers.ast` module provides the building blocks for that.
"""

from __future__ import annotations

import logging
import typing
from enum import Enum
from xml.etree.ElementTree import Element, QName, TreeBuilder

from defusedxml.ElementTree import DefusedXMLParser, ParseError

from gisserver.exceptions import ExternalParsingError

logger = logging.getLogger(__name__)

__all__ = (
    "xmlns",
    "NSElement",
    "parse_xml_from_string",
    "parse_qname",
    "split_ns",
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
        return f"{{{self.value}}}{local_name}"  # same as QName(..).text


class NSElement(Element):
    """Custom XML element, which also exposes its original namespace aliases.
    That information is needed to parse text content and attributes in WFS
    that hold a QName value. For example:

    * ``<ValueReference>ns0:elementName</ValueReference>``
    * ``<Query typeNames="ns1:name">``
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ns_aliases = {}  # assigned by NSTreeBuilder, in {prefix: uri} format.

    def parse_qname(self, qname: str) -> str:
        """Resolve an aliased QName value to its fully qualified name."""
        return parse_qname(qname, self.ns_aliases)

    def get_attribute(self, name: str) -> str:
        """Resolve an attribute, raise an error when it's missing."""
        try:
            return self.attrib[name]
        except KeyError:
            raise ExternalParsingError(
                f"Element {self.tag} misses required attribute '{name}'"
            ) from None

    if typing.TYPE_CHECKING:
        # Make sure the type checking knows the actual type of the elements.
        def find(self, path: str, namespaces: dict[str, str] | None = None) -> NSElement | None:
            return super().find(path, namespaces)

        def findall(self, path: str, namespaces: dict[str, str] | None = None) -> list[NSElement]:
            return super().findall(path, namespaces)

        def __iter__(self) -> typing.Iterator[NSElement]:
            return super().__iter__()


def parse_qname(qname: str | None, ns_aliases: dict) -> str | None:
    """Resolve the QName aliases.

    For example, ``gml:Point`` will be resolved to ``{http://www.opengis.net/gml/3.2}Point``.
    The XML namespace prefix is a custom alias, so if "ns0" is declared as "http://www.opengis.net/gml/3.2",
    it means "ns0:Point" should resolve to the same fully qualified type name.
    """
    if not qname:
        return None

    if "/" in qname:
        raise ExternalParsingError(f"Can't resolve QName '{qname}', this is an XPath notation.")

    # Allow resolving @gml:id, remove the @ sigm.
    is_attribute = qname[0] == "@"
    if is_attribute:
        qname = qname[1:]

    prefix, _, localname = qname.rpartition(":")
    if not prefix and "" not in ns_aliases:
        full_name = localname
    else:
        try:
            uri = ns_aliases[prefix]
        except KeyError:
            logger.debug("Can't resolve QName '%s', available namespaces: %r", qname, ns_aliases)
            raise ExternalParsingError(
                f"Can't resolve QName '{qname}', an XML namespace declaration is missing."
            ) from None
        full_name = QName(uri, localname).text

    return f"@{full_name}" if is_attribute else full_name


class NSTreeBuilder(TreeBuilder):
    """Custom TreeBuilder to track namespaces."""

    def __init__(self, **kwargs):
        super().__init__(element_factory=NSElement, **kwargs)
        self.ns_stack = [{}]

    def start(self, tag, attrs):
        super().start(tag, attrs)
        self.ns_stack.append({})  # reserve stack for child tags

    def start_ns(self, prefix, uri):
        self.ns_stack[-1][prefix] = uri

    def end(self, tag) -> Element:
        element = super().end(tag)
        self.ns_stack.pop()  # clear reservation for child tags
        element.ns_aliases = self._flatten_ns()
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
        logger.debug("Parsing XML error: %s: %s", e, xml_string)
        raise ExternalParsingError(str(e)) from e


def split_ns(tag_or_value: str) -> tuple[str | None, str]:
    """Split the element tag or attribute/text value into the namespace and
    local name. The stdlib etree doesn't have the properties for this (lxml does).
    """
    # Tags may start with a `{ns}`
    if tag_or_value.startswith("{"):
        end = tag_or_value.index("}")
        return tag_or_value[1:end], tag_or_value[end + 1 :]
    # Attribute/text values may start with `ns:`
    elif tag_or_value.find(":") >= 0:
        end = tag_or_value.index(":")
        return tag_or_value[1:end], tag_or_value[end + 1 :]
    else:
        return None, tag_or_value
