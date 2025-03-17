"""Generic support for various GML versions.

These functions locate GML objects, and redirect to the proper parser.
"""

from __future__ import annotations

from typing import Union
from xml.etree.ElementTree import Element

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.ast import tag_registry
from gisserver.parsers.xml import parse_xml_from_string

from .base import AbstractGeometry, GM_Envelope, GM_Object, TM_Object
from .geometries import is_gml_element  # also do tag registration

# All known root nodes as GML object:
GmlRootNodes = Union[GM_Object, GM_Envelope, TM_Object]

__all__ = [
    "GM_Object",
    "GM_Envelope",
    "TM_Object",
    "AbstractGeometry",
    "parse_gml",
    "parse_gml_node",
    "find_gml_nodes",
]


def parse_gml(text: str | bytes) -> GmlRootNodes:
    """Parse an XML <gml:...> string."""
    root_element = parse_xml_from_string(text)
    return parse_gml_node(root_element)


def parse_gml_node(element: Element) -> GmlRootNodes:
    """Parse the element"""
    if not is_gml_element(element):
        raise ExternalParsingError(f"Expected GML namespace for {element.tag}")

    # All known root nodes as GML object:
    return tag_registry.node_from_xml(element, allowed_types=GmlRootNodes.__args__)


def find_gml_nodes(element: Element) -> list[Element]:
    """Find all gml elements in a node"""
    result = []
    for child in element:
        # This selects all GML elements, including 2.1
        if is_gml_element(child):
            result.append(child)

    return result
