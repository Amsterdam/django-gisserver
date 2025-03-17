from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from itertools import chain
from typing import TypeVar
from xml.etree.ElementTree import Element, QName

from gisserver.exceptions import ExternalParsingError


class TagNameEnum(Enum):
    """An enumeration of XML tag names.

    All enumerations that represent tag names inherit from this.
    Each member name should be exactly the XML tag that it refers to.
    """

    @classmethod
    def from_xml(cls, element: Element):
        """Cast the element tag name into the enum member"""
        tag_name = element.tag
        if tag_name.startswith("{"):
            # Split the element tag into the namespace and local name.
            # The stdlib etree doesn't have the properties for this (lxml does).
            end = tag_name.index("}")
            tag_name = tag_name[end + 1 :]

        return cls[tag_name]

    @classmethod
    def _missing_(cls, value):
        raise NotImplementedError(f"<{value}> is not registered as valid {cls.__name__}")

    def __repr__(self):
        # Make repr(filter) easier to copy-paste
        return f"{self.__class__.__name__}.{self.name}"


class BaseNode:
    """The base node for all classes that represent an XML tag.

    All subclasses of this class build an Abstract Syntax Tree (AST)
    that describes the XML content in Python objects. Each object can handle
    implement additional logic to

    Each subclass should implement the :meth:`from_xml` to translate
    an XML tag into a Python (data) class.
    """

    xml_ns = None
    xml_tags = []

    def __init_subclass__(cls):
        # Each class level has a fresh list of supported child tags.
        cls.xml_tags = []

    @classmethod
    def from_xml(cls, element: Element):
        """Initialize this Python class from the data of the corresponding XML tag.
        Each subclass overrides this to implement the XMl parsing of that particular XML tag.
        """
        raise NotImplementedError(
            f"{cls.__name__}.from_xml() is not implemented to parse <{element.tag}>"
        )

    @classmethod
    def from_child_xml(cls, element: Element) -> BaseNode:
        """Parse the element, returning the correct subclass of this tag.

        When ``Expression.from_child_xml(some_node)`` is given, it may
        return a ``Literal``, ``ValueReference``, ``Function`` or ``BinaryOperator`` node.
        """
        sub_class = tag_registry.resolve_class(element, allowed_types=(cls,))
        return sub_class.from_xml(element)

    @classmethod
    def get_tag_names(cls) -> Iterable[str]:
        """Provide all known XMl tags that this code can parse."""
        return chain.from_iterable(sub_type.xml_tags for sub_type in cls.__subclasses__())


BN = TypeVar("BN", bound=BaseNode)


class TagRegistry:
    """Registration of all classes that can parse XML nodes.

    The same class can be registered multiple times for different tag names.
    """

    parsers: dict[str, type[BaseNode]]

    def __init__(self):
        self.parsers = {}

    def register(
        self,
        tag: str | type[TagNameEnum] | None = None,
        namespace: str | None = None,
        hidden: bool = False,
    ):
        """Decorator to register a class as XML element parser.

        Usage:

            @dataclass
            @tag_registry.register()
            class SomeXmlTag(BaseNode):
                xml_ns = FES

                @classmethod
                def from_xml(cls, element: Element):
                    return cls(
                        ...
                    )

        Whenever an element of the registered XML name is found,
        the given "SomeXmlTag" will be initialized.

        It's also possible to register tag names using an enum;
        each member name is assumed to be an XML tag name.
        """

        def _dec(node_class: type[BaseNode]) -> type[BaseNode]:
            if tag is None or isinstance(tag, str):
                # Single tag name for the class.
                self._register_tag_parser(
                    node_class, tag=tag or node_class.__name__, namespace=namespace, hidden=hidden
                )
            elif issubclass(tag, TagNameEnum):
                # Allow tags to be an Enum listing possible tag names.
                # Note using __members__, not _member_names_.
                # The latter will skip aliased items (like BBOX/Within).
                for member_name in tag.__members__:
                    self._register_tag_parser(node_class, tag=member_name, namespace=namespace)
            else:
                raise TypeError("tag type incorrect")

            return node_class

        return _dec

    def _register_tag_parser(
        self,
        node_class: type[BaseNode],
        tag: str,
        namespace: str | None = None,
        hidden: bool = False,
    ):
        """Register a Python (data) class as parser for an XML node."""
        if namespace is None and node_class.xml_ns is None:
            raise RuntimeError(
                f"{node_class.__name__}.xml_ns should be set, or namespace should be given."
            )

        qname = QName((namespace or node_class.xml_ns), tag=tag)
        if qname.text in self.parsers:
            raise RuntimeError(f"Another class is already registered to parse the <{qname}> tag.")

        self.parsers[qname.text] = node_class  # Track this parser to resolve the tag.
        if not hidden:
            node_class.xml_tags.append(tag)  # Allow fetching all names later

    def from_child_xml(self, element: Element, allowed_types: tuple[type[BN]] | None = None) -> BN:
        """Find the ``BaseNode`` subclass that corresponds to the given XML element,
        and initialize it with the element. This is a convenience shortcut.
        ``"""
        node_class = self.resolve_class(element, allowed_types)
        return node_class.from_xml(element)

    def resolve_class(
        self, element: Element, allowed_types: tuple[type[BN]] | None = None
    ) -> type[BN]:
        """Find the ``BaseNode`` subclass that corresponds to the given XML element."""
        try:
            node_class = self.parsers[element.tag]
        except KeyError:
            msg = f"Unsupported tag: <{element.tag}>"
            if allowed_types:
                # Show better exception message
                types = ", ".join(c.__name__ for c in allowed_types)
                msg = f"{msg}, expected one of: {types}"

            raise ExternalParsingError(msg) from None

        # Check whether the resolved class is indeed a valid option here.
        if allowed_types is not None and not issubclass(node_class, allowed_types):
            types = ", ".join(c.__name__ for c in allowed_types)
            raise ExternalParsingError(
                f"Unexpected {node_class.__name__} for <{element.tag}> node, "
                f"expected one of: {types}"
            )

        return node_class


tag_registry = TagRegistry()
