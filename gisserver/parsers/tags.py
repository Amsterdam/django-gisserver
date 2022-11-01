from __future__ import annotations

from functools import wraps
from itertools import chain
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, QName

from gisserver.exceptions import ExternalParsingError


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
