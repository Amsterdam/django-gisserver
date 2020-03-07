"""These classes map to the FES 2.0 specification for expressions.
The class names are identical to those in the FES spec.
"""
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Union
from xml.etree.ElementTree import Element

from gisserver.parsers.base import FES20, BaseNode, tag_registry
from gisserver.parsers.utils import expect_tag

NoneType = type(None)


class Expression(BaseNode):
    """Abstract base class, as defined by FES spec."""

    xml_ns = FES20


@dataclass
@tag_registry.register("Literal")
class Literal(Expression):
    """The <fes:Literal> element that holds a literal value"""

    value: Union[str, date, NoneType]  # officially <xsd:any>
    type: Optional[str] = None

    def __str__(self):
        return self.value

    @classmethod
    @expect_tag(FES20, "Literal")
    def from_xml(cls, element: Element):
        # Cast the value based on the given xsd:QName
        type = element.get("type")
        value = element.text
        if type:
            if type == "xs:date":
                value = date.fromisoformat(value)
            elif type == "xsd:string":
                pass
            else:
                raise NotImplementedError(
                    f'<fes:Literal type="{type}"> is not implemented.'
                )

        return cls(value=value, type=type)


@dataclass
@tag_registry.register("ValueReference")
class ValueReference(Expression):
    """The <fes:ValueReference> element that holds an XPath string.
    In the fes XSD, this is declared as a subclass of xsd:string.
    """

    xpath: str

    def __str__(self):
        return self.xpath

    @classmethod
    @expect_tag(FES20, "ValueReference")
    def from_xml(cls, element: Element):
        return cls(xpath=element.text)


@dataclass
@tag_registry.register("Function")
class Function(Expression):
    """The <fes:Function name="..."> element."""

    name: str  # scoped name
    arguments: List[Expression]  # xsd:element ref="fes20:expression"

    @classmethod
    @expect_tag(FES20, "Function")
    def from_xml(cls, element: Element):
        return cls(
            name=element.attrib["name"],
            arguments=[Expression.from_child_xml(child) for child in element],
        )
