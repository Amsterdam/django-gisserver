"""Additional parsing logic for GML values.

Most GML elements are parsed through GeoDjango by using the GEOSGeometry element.
"""

from __future__ import annotations

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.ast import tag_registry
from gisserver.parsers.xml import NSElement, parse_xml_from_string

from .base import AbstractGeometry, GM_Envelope, GM_Object, TM_Object
from .geometries import GEOSGMLGeometry, is_gml_element  # also do tag registration

__all__ = [
    "GM_Object",
    "GM_Envelope",
    "TM_Object",
    "AbstractGeometry",
    "GEOSGMLGeometry",
    "parse_gml",
    "parse_gml_node",
    "find_gml_nodes",
]


def parse_gml(text: str | bytes) -> GM_Object | GM_Envelope | TM_Object:
    """Parse an XML <gml:...> string."""
    root_element = parse_xml_from_string(text)
    return parse_gml_node(root_element)


def parse_gml_node(element: NSElement) -> GM_Object | GM_Envelope | TM_Object:
    """Parse the GML element."""
    if not is_gml_element(element):
        raise ExternalParsingError(f"Expected GML namespace for {element.tag}")

    # All known root nodes as GML object:
    return tag_registry.node_from_xml(element, allowed_types=(GM_Object, GM_Envelope, TM_Object))


def find_gml_nodes(element: NSElement) -> list[NSElement]:
    """Find all ``<gml:...>`` elements in a node.
    This selects all GML elements, including GML 2.1 tags.
    """
    return [child for child in element if is_gml_element(child)]
