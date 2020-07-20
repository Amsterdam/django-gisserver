import re
from decimal import Decimal as D
from functools import wraps
from typing import List, Optional, Tuple
from xml.etree.ElementTree import Element, QName

from gisserver.exceptions import ExternalParsingError
from gisserver.types import parse_iso_datetime

RE_FLOAT = re.compile(r"\A[0-9]+(\.[0-9]+)\Z")


def expect_tag(namespace, *tag_names, leaf=False):
    """Validate whether a given tag is need"""
    valid_tags = set(str(QName(namespace, name)) for name in tag_names)
    expect0 = str(QName(namespace, tag_names[0]))

    def _wrapper(func):
        @wraps(func)
        def _from_xml_expect(cls, element, *args, **kwargs):
            if element.tag not in valid_tags:
                raise ExternalParsingError(
                    f"{cls.__name__}.{func.__name__}(element) expects an <{expect0}> node, "
                    f"got <{element.tag}>"
                )
            if leaf and len(element):
                raise ExternalParsingError(
                    f"Unsupported child element for {element.tag} element: {element[0].tag}."
                )

            return func(cls, element, *args, **kwargs)

        return _from_xml_expect

    return _wrapper


def get_child(root, namespace, localname) -> Element:
    """Find the element using a fully qualified name."""
    return root.find(QName(namespace, localname).text)


def get_children(root, namespace, localname) -> List[Element]:
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


def split_ns(tag_name: str) -> Tuple[Optional[str], str]:
    """Split the element tag into the namespace and local name.
    The stdlib etree doesn't have the properties for this (lxml does).
    """
    if tag_name.startswith("{"):
        end = tag_name.index("}")
        return tag_name[1:end], tag_name[end + 1 :]
    else:
        return None, tag_name


def auto_cast(value: str):
    """Automatically cast a value to a scalar."""
    if value.isdigit():
        return int(value)
    elif RE_FLOAT.match(value):
        return D(value)
    elif "T" in value:
        try:
            return parse_iso_datetime(value)
        except ValueError:
            pass

    return value
