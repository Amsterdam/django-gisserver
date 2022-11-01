"""Generic support for various GML versions.

These functions locate GML objects, and redirect to the proper parser.
"""
from __future__ import annotations

from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.base import tag_registry

from .base import AbstractGeometry, GM_Envelope, GM_Object, TM_Object
from .geometries import is_gml_element  # also do tag registration

# All known root nodes as GML object:
FES_GML_NODES = (GM_Object, GM_Envelope, TM_Object)

__all__ = [
    "GM_Object",
    "GM_Envelope",
    "TM_Object",
    "AbstractGeometry",
    "parse_gml",
    "parse_gml_node",
    "find_gml_nodes",
]


def parse_gml(text: str | bytes) -> FES_GML_NODES:
    """Parse an XML <gml:...> string."""
    root_element = fromstring(text)
    return parse_gml_node(root_element)


def parse_gml_node(element: Element) -> FES_GML_NODES:
    """Parse the element"""
    if not is_gml_element(element):
        raise ExternalParsingError(f"Expected GML namespace for {element.tag}")

    return tag_registry.from_child_xml(element, allowed_types=FES_GML_NODES)


def find_gml_nodes(element: Element) -> list[Element]:
    """Find all gml elements in a node"""
    result = []
    for child in element:
        # This selects all GML elements, including 2.1
        if is_gml_element(child):
            result.append(child)

    return result
