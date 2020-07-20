from enum import Enum
from typing import Dict, Type
from xml.etree.ElementTree import Element, QName
from gisserver.exceptions import ExternalParsingError
from .utils import split_ns


class TagNameEnum(Enum):
    """An enumeration of tag names.

    All enumerations that represent tag names inherit from this.
    Each member name should be exactly the XML tag that it refers to.
    """

    @classmethod
    def from_xml(cls, element: Element):
        """Cast the element tag name into the enum member"""
        ns, localname = split_ns(element.tag)
        return cls[localname]

    @classmethod
    def _missing_(cls, value):
        raise NotImplementedError(
            f"<{value}> is not registered as valid {cls.__name__}"
        )

    def __repr__(self):
        # Make repr(filter) easier to copy-paste
        return f"{self.__class__.__name__}.{self.name}"


class BaseNode:
    """The base node for all classes that represent an XML tag."""

    xml_ns = None
    xml_tags = []

    @classmethod
    def from_xml(cls, element: Element):
        raise NotImplementedError(
            f"{cls.__name__}.from_xml() is not implemented to parse <{element.tag}>"
        )

    @classmethod
    def from_child_xml(cls, element: Element) -> "BaseNode":
        """By default, the node attempts to locate a child-class from the registry.
        The individual tags should override `from_xml()` to return their own type.
        """
        return tag_registry.from_child_xml(element, allowed_types=(cls,))


class TagRegistry:
    """Registration of all classes that can parse XML nodes.

    The same class can be registered multiple times for different tag names.
    """

    parsers: Dict[str, Type[BaseNode]]

    def __init__(self):
        self.parsers = {}

    def register(self, name=None, namespace=None):
        """Decorator to register an class as XML node parser.

        This registers the decorated class as the designated parser
        for a specific XML tag.

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

        """

        def _dec(sub_class: Type[BaseNode]) -> Type[BaseNode]:
            if sub_class.xml_ns is None:
                raise RuntimeError(f"{sub_class.__name__}.xml_ns should be set")

            localname = name or sub_class.__name__
            qname = QName(namespace or sub_class.xml_ns, localname)

            self.parsers[qname] = sub_class  # Track this parser to resolve the tag.
            sub_class.xml_tags.append(name)  # Allow fetching all names later
            return sub_class  # allow decorator usage

        return _dec

    def register_names(self, names: Type[TagNameEnum], namespace=None):
        """Decorator to register the 'tag_class' as the
        parser-backend for all member-names in this enum.
        """

        def _dec(sub_class: Type[BaseNode]):
            # Looping over _member_names_ will skip aliased items (like BBOX/Within)
            for member_name in names.__members__.keys():
                self.register(name=member_name, namespace=namespace)(sub_class)
            return sub_class

        return _dec

    def from_child_xml(self, element: Element, allowed_types=None) -> BaseNode:
        """Convert the element into a Python class.

        This locates the parser from the registered tag.
        It's assumed that the tag has an "from_xml()" method too.
        """
        real_cls = self.resolve_class(element.tag)

        # Check whether the resolved class is indeed a valid option here.
        if allowed_types is not None and not issubclass(real_cls, allowed_types):
            types = ", ".join(c.__name__ for c in allowed_types)
            raise ExternalParsingError(
                f"Unexpected {real_cls.__name__} for <{element.tag}> node, "
                f"expected one of: {types}"
            )

        return real_cls.from_xml(element)

    def resolve_class(self, tag_name) -> Type[BaseNode]:
        # Resolve the dataclass using the tag name
        try:
            return self.parsers[tag_name]
        except KeyError:
            raise NotImplementedError(f"Unsupported tag: <{tag_name}>") from None


tag_registry = TagRegistry()
