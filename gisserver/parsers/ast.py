"""Utilities for building an Abstract Syntax Tree (AST) from an XML fragment.

By transforming the XML Element nodes into Python objects, most logic naturally follows.
For example, the FES filter syntax can be processed into objects that build an ORM query.

Python classes can inherit :class:`AstNode` and register themselves as the parser/handler
for a given tag. Both normal Python classes and dataclass work,
as long as it has an :meth:`AstNode.from_xml` class method.
The custom ``from_xml()`` method should copy the XML data into local attributes.

Next, when :meth:`TagRegistry.node_from_xml` is called,
it will detect which class the XML Element refers to and initialize it using the ``from_xml()`` call.
As convenience, calling a :meth:`AstNode.child_from_xml`
on a subclass will also initialize the right subclass and initialize it.

Since clients may not follow the desired XML schema, and make mistakes, we should guard against
creating an invalid Abstract Syntax Tree. When using :meth:`TagRegistry.node_from_xml`,
the allowed child types can also be provided, preventing invalid child elements.
Furthermore, to support the creation of ``from_xml()`` methods, the :func:`expect_tag`,
:func:`expect_children` and :func:`expect_no_children` decorators validate
whether the given tag has the expected elements. This combination should make it easy
to validate whether a provided XML structure confirms to the supported schema.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from functools import wraps
from typing import TypeVar
from xml.etree.ElementTree import QName

from django.utils.functional import classproperty

from gisserver.exceptions import InvalidXmlElement, XmlElementNotSupported
from gisserver.parsers.xml import NSElement, xmlns

__all__ = (
    "TagNameEnum",
    "AstNode",
    "TagRegistry",
    "tag_registry",
    "expect_children",
    "expect_tag",
    "expect_no_children",
)


class TagNameEnum(Enum):
    """An base clas for enumerations of XML tag names.

    All enumerations that represent tag names inherit from this.
    Each member name should be exactly the XML tag that it refers to.
    """

    @classmethod
    def from_xml(cls, element: NSElement):
        """Cast the element tag name into the enum member.

        This translates the element name
        such as ``{http://www.opengis.net/fes/2.0}PropertyIsEqualTo``
        into a ``PropertyIsEqualTo`` member.
        """
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


class AstNode:
    """The base node for all classes that represent an XML tag.

    All subclasses of this class build an Abstract Syntax Tree (AST)
    that describes the XML content in Python objects. Each object can handle
    implement additional logic to

    Each subclass should implement the :meth:`from_xml` to translate
    an XML tag into a Python (data) class.
    """

    #: Default namespace of the element and subclasses, if not given by ``@tag_registry.register()``.
    xml_ns: xmlns | str | None = None

    _xml_tags = []

    @classproperty
    def xml_name(cls) -> str:
        """Tell the default tag by which this class is registered"""
        return cls._xml_tags[0]

    xml_name.__doc__ = "Tell the default tag by which this class is registered"

    def __init_subclass__(cls):
        # Each class level has a fresh list of supported child tags.
        cls._xml_tags = []

    @classmethod
    def from_xml(cls, element: NSElement):
        """Initialize this Python class from the data of the corresponding XML tag.
        Each subclass overrides this to implement the XML parsing of that particular XML tag.
        """
        raise NotImplementedError(
            f"{cls.__name__}.from_xml() is not implemented to parse <{element.tag}>"
        )

    @classmethod
    def child_from_xml(cls, element: NSElement) -> AstNode:
        """Parse the element, returning the correct subclass of this tag.

        When ``Expression.child_from_xml(some_node)`` is given, it may
        return a ``Literal``, ``ValueReference``, ``Function`` or ``BinaryOperator`` node.
        """
        sub_class = tag_registry.resolve_class(element, allowed_types=(cls,))
        return sub_class.from_xml(element)

    @classmethod
    def get_tag_names(cls) -> list[str]:
        """Provide all known XML tags that this code can parse."""
        try:
            # Because a cached class property is hard to build
            return _KNOWN_TAG_NAMES[cls]
        except KeyError:
            all_xml_tags = cls._xml_tags.copy()
            for sub_cls in cls.__subclasses__():
                all_xml_tags.extend(sub_cls.get_tag_names())
            _KNOWN_TAG_NAMES[cls] = all_xml_tags
            return all_xml_tags


_KNOWN_TAG_NAMES = {}

BaseNode = AstNode  # keep old name around
A = TypeVar("A", bound=AstNode)


class TagRegistry:
    """Registration of all classes that can parse XML nodes.

    The same class can be registered multiple times for different tag names.
    """

    parsers: dict[str, type[AstNode]]

    def __init__(self):
        self.parsers = {}

    def register(
        self,
        tag: str | type[TagNameEnum] | None = None,
        namespace: xmlns | str | None = None,
        hidden: bool = False,
    ):
        """Decorator to register a class as XML element parser.

        Usage:

        .. code-block:: python

            @dataclass
            @tag_registry.register()
            class SomeXmlTag(AstNode):
                xml_ns = FES

                @classmethod
                def from_xml(cls, element: NSElement):
                    return cls(
                        ...
                    )

        Whenever an element of the registered XML name is found,
        the given "SomeXmlTag" will be initialized.

        It's also possible to register tag names using an enum;
        each member name is assumed to be an XML tag name.
        """

        def _dec(node_class: type[AstNode]) -> type[AstNode]:
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
                    self._register_tag_parser(
                        node_class, tag=member_name, namespace=namespace, hidden=hidden
                    )
            else:
                raise TypeError("tag type incorrect")

            return node_class

        return _dec

    def _register_tag_parser(
        self,
        node_class: type[AstNode],
        tag: str,
        namespace: xmlns | str | None = None,
        hidden: bool = False,
    ):
        """Register a Python (data) class as parser for an XML node."""
        if not issubclass(node_class, AstNode):
            raise TypeError(f"{node_class} must be a subclass of AstNode")

        if namespace is None and node_class.xml_ns is None:
            raise RuntimeError(
                f"{node_class.__name__}.xml_ns should be set, or namespace should be given."
            )

        xml_name = QName((namespace or node_class.xml_ns), tag=tag).text
        if xml_name in self.parsers:
            raise RuntimeError(
                f"Another class is already registered to parse the <{xml_name}> tag."
            )

        self.parsers[xml_name] = node_class  # Track this parser to resolve the tag.
        if not hidden:
            node_class._xml_tags.append(xml_name)  # Allow fetching all names later

    def node_from_xml(self, element: NSElement, allowed_types: tuple[type[A]] | None = None) -> A:
        """Find the ``AstNode`` subclass that corresponds to the given XML element,
        and initialize it with the element. This is a convenience shortcut.
        """
        node_class = self.resolve_class(element, allowed_types)
        return node_class.from_xml(element)

    def resolve_class(
        self, element: NSElement, allowed_types: tuple[type[A]] | None = None
    ) -> type[A]:
        """Find the :class:`AstNode` subclass that corresponds to the given XML element."""
        try:
            node_class = self.parsers[element.tag]
        except KeyError:
            msg = f"Unsupported tag: <{element.qname}>"
            if "{" not in element.tag:
                msg = f"{msg} without an XML namespace"
            if allowed_types:
                allowed = _tag_names_to_text(_get_allowed_tag_names(*allowed_types), element)
                msg = f"{msg}, expected one of: {allowed}."

            raise XmlElementNotSupported(msg) from None

        # Check whether the resolved class is indeed a valid option here.
        if allowed_types is not None and not issubclass(node_class, allowed_types):
            types = ", ".join(c.__name__ for c in allowed_types)
            raise InvalidXmlElement(
                f"Unexpected {node_class.__name__} for <{element.qname}> node, "
                f"expected one of: {types}"
            )

        return node_class

    def get_parser_class(self, xml_qname) -> type[AstNode]:
        """Provide the parser class for a given XML Qualified name."""
        return self.parsers[xml_qname]

    def find_subclasses(self, node_type: type[A]) -> list[type[A]]:
        """Find all registered parsers for a given node."""
        return {
            tag: node_class
            for tag, node_class in self.parsers.items()
            if issubclass(node_class, node_type)
        }


def expect_tag(namespace: xmlns | str, *tag_names: str):
    """Decorator for ``from_xml()`` methods that validate whether a given tag is provided.

    For example:

    .. code-block:: python

        @classmethod
        @expect_tag(xmlns.fes20, "Literal")
        def from_xml(cls, element):
            ...

    This guard is needed when nodes are passed directly to a ``from_xml()`` method.
    """
    valid_tags = {QName(namespace, name).text for name in tag_names}
    expect0 = QName(namespace, tag_names[0]).text

    def _wrapper(func):
        @wraps(func)
        def _expect_tag_decorator(cls, element: NSElement, *args, **kwargs):
            if element.tag not in valid_tags:
                raise InvalidXmlElement(
                    f"{cls.__name__} parser expects an <{_replace_common_ns(expect0, element)}> node,"
                    f" got <{element.qname}>"
                )
            return func(cls, element, *args, **kwargs)

        return _expect_tag_decorator

    return _wrapper


def expect_no_children(from_xml_func):
    """Decorator for ``from_xml()`` methods that validate that the XML tag has no child nodes.

    For example:

    .. code-block:: python

        @classmethod
        @expect_tag(xmlns.fes20, "ResourceId")
        @expect_no_children
        def from_xml(cls, element):
            ...
    """

    @wraps(from_xml_func)
    def _expect_no_children_decorator(cls, element: NSElement, *args, **kwargs):
        if len(element):
            raise InvalidXmlElement(
                f"Element <{element.qname}> does not support child elements,"
                f" found <{element[0].qname}>."
            )

        return from_xml_func(cls, element, *args, **kwargs)

    return _expect_no_children_decorator


def expect_children(  # noqa: C901
    min_child_nodes, *expect_types: str | type[AstNode], silent_allowed: tuple[str] = ()
):
    """Decorator for ``from_xml()`` methods to validate whether an element has the expected children.

    For example:

    .. code-block:: python

        @classmethod
        @expect_children(2, Expression)
        def from_xml(cls, element):
            ...
    """
    # Validate arguments early
    for child_type in expect_types + silent_allowed:
        if isinstance(child_type, str):
            if not child_type.startswith("{"):
                raise ValueError(
                    f"String arguments to @expect_children() should be"
                    f" fully qualified XML namespaces, not {child_type!r}"
                )
        elif not isinstance(child_type, type) or not issubclass(child_type, AstNode):
            raise TypeError(f"Unexpected {child_type!r}")

    def _get_allowed(known_tag_names, element):
        return _tag_names_to_text(sorted(set(known_tag_names) - set(silent_allowed)), element)

    def _wrapper(func):
        @wraps(func)
        def _expect_children_decorator(cls, element: NSElement, *args, **kwargs):
            known_tag_names = _get_allowed_tag_names(*expect_types, *silent_allowed)

            if len(element) < min_child_nodes:
                allowed = _get_allowed(known_tag_names, element)
                raise InvalidXmlElement(
                    f"<{element.qname}> should have {min_child_nodes} child nodes,"
                    f" got only {len(element)}."
                    f" Allowed types are: {allowed}."
                )
            for child in element:
                if child.tag not in known_tag_names:
                    allowed = _get_allowed(known_tag_names, element)
                    raise InvalidXmlElement(
                        f"<{element.qname}> does not support a <{child.qname}> child node."
                        f" Allowed types are: {allowed}."
                    )

            return func(cls, element, *args, **kwargs)

        return _expect_children_decorator

    return _wrapper


def _get_allowed_tag_names(*expect_types: type[AstNode] | str) -> list[str]:
    # Resolve arguments later, as get_tag_names() depends on __subclasses__()
    # which may not be completely known at this point.
    tag_names = []
    for child_type in expect_types:
        if isinstance(child_type, type) and issubclass(child_type, AstNode):
            tag_names.extend(child_type.get_tag_names())
        elif isinstance(child_type, str):
            if not child_type.startswith("{"):
                raise ValueError(
                    f"String arguments should be fully qualified XML namespaces, not {child_type!r}"
                )
            tag_names.append(child_type)
        else:
            raise TypeError(f"Unexpected {child_type!r}")
    return tag_names


def _tag_names_to_text(tag_names: Iterable[str], user_element: NSElement) -> str:
    body = _replace_common_ns(">, <".join(tag_names), user_element)
    return f"<{body}>"


def _replace_common_ns(text: str, user_element: NSElement):
    """In error messages, replace the full XML names with QName/prefixed versions.
    The chosen prefixes reference the tags that the client submitted in their XML body.
    """
    for prefix, ns in user_element.ns_aliases.items():
        text = text.replace(f"{{{ns}}}", f"{prefix}:")
    return text


#: The tag registry to register new parsing classes at.
tag_registry = TagRegistry()
