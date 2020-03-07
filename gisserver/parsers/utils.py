from functools import wraps
from typing import List, Optional, Tuple
from xml.etree.ElementTree import Element, QName


def expect_tag(namespace, tag_name):
    """Validate whether a given tag is need"""

    def _wrapper(func):
        @wraps(func)
        def _from_xml_expect(cls, element):
            qname = QName(namespace, tag_name)
            if element.tag != qname:
                raise ValueError(
                    f"{cls.__name__}.{func.__name__}(element) expects an <{qname}> node, "
                    f"got <{element.tag}>"
                )

            return func(cls, element)

        return _from_xml_expect

    return _wrapper


def get_child(root, namespace, localname) -> Element:
    """Find the element using a fully qualified name."""
    return root.find(QName(namespace, localname).text)


def get_children(root, namespace, localname) -> List[Element]:
    """Find the element using a fully qualified name."""
    return root.findall(QName(namespace, localname).text)


def split_ns(element) -> Tuple[Optional[str], str]:
    """Split the element tag into the namespace and local name.
    The stdlib etree doesn't have the properties for this (lxml does).
    """
    if element.tag.startswith("{"):
        end = element.tag.index("}")
        return element.tag[1:end], element.tag[end + 1 :]
    else:
        return None, element.tag
