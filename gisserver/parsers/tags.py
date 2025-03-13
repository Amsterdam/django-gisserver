from __future__ import annotations

from functools import wraps
from itertools import chain
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, QName, TreeBuilder

from defusedxml.ElementTree import DefusedXMLParser, ParseError

from gisserver.exceptions import ExternalParsingError


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


def expect_tag(namespace: str, *tag_names: str, leaf=False):
    """Validate whether a given tag is need"""
    valid_tags = {str(QName(namespace, name)) for name in tag_names}
    expect0 = str(QName(namespace, tag_names[0]))

    def _wrapper(func):
        @wraps(func)
        def _expect_tag_decorator(cls, element: Element, *args, **kwargs):
            if element.tag not in valid_tags:
                raise ExternalParsingError(
                    f"{cls.__name__} parser expects an <{expect0}> node, got <{element.tag}>"
                )
            if leaf and len(element):
                raise ExternalParsingError(
                    f"Unsupported child element for {element.tag} element: {element[0].tag}."
                )

            return func(cls, element, *args, **kwargs)

        return _expect_tag_decorator

    return _wrapper


def expect_children(min_child_nodes, *expect_types: str | type[BaseNode]):
    def _wrapper(func):
        @wraps(func)
        def _expect_children_decorator(cls, element: Element, *args, **kwargs):
            if len(element) < min_child_nodes:
                type_names = ", ".join(
                    sorted(
                        set(
                            chain.from_iterable(
                                (
                                    [child_type]
                                    if isinstance(child_type, str)
                                    else chain.from_iterable(
                                        sub_type.xml_tags
                                        for sub_type in child_type.__subclasses__()
                                    )
                                )
                                for child_type in expect_types
                            )
                        )
                    )
                )
                suffix = f" (possible tags: {type_names})" if type_names else ""
                raise ExternalParsingError(
                    f"<{element.tag}> should have {min_child_nodes} child nodes, "
                    f"got {len(element)}{suffix}"
                )

            return func(cls, element, *args, **kwargs)

        return _expect_children_decorator

    return _wrapper


def get_child(root, namespace, localname) -> Element:
    """Find the element using a fully qualified name."""
    return root.find(QName(namespace, localname).text)


def get_children(root, namespace, localname) -> list[Element]:
    """Find the element using a fully qualified name."""
    return root.findall(QName(namespace, localname).text)


def get_attribute(element: Element, name) -> str:
    """Resolve an attribute, raise an error when it's missing."""
    try:
        return element.attrib[name]
    except KeyError:
        raise ExternalParsingError(
            f"Element {element.tag} misses required attribute '{name}'"
        ) from None


def split_ns(tag_name: str) -> tuple[str | None, str]:
    """Split the element tag into the namespace and local name.
    The stdlib etree doesn't have the properties for this (lxml does).
    """
    if tag_name.startswith("{"):
        end = tag_name.index("}")
        return tag_name[1:end], tag_name[end + 1 :]
    else:
        return None, tag_name


if TYPE_CHECKING:
    from gisserver.parsers.base import BaseNode
