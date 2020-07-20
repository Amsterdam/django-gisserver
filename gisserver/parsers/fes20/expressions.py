"""These classes map to the FES 2.0 specification for expressions.
The class names are identical to those in the FES spec.
"""
import operator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal as D
from django.db import models
from django.utils.functional import cached_property
from typing import List, Optional, Tuple, Union
from xml.etree.ElementTree import Element

from django.contrib.gis.geos import GEOSGeometry
from django.db.models import Func, Q, Value
from django.db.models.expressions import Combinable

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.base import BaseNode, TagNameEnum, tag_registry
from gisserver.parsers.fes20.functions import function_registry
from gisserver.parsers.gml import (
    GM_Envelope,
    GM_Object,
    TM_Object,
    is_gml_element,
    parse_gml_node,
)
from gisserver.parsers.utils import auto_cast, expect_tag, get_attribute
from gisserver.types import ORMPath, FES20, XsdTypes, split_xml_name

NoneType = type(None)
RhsTypes = Union[
    Combinable, Func, Q, GEOSGeometry, bool, int, str, date, datetime, tuple
]
ParsedValue = Union[
    int, str, date, D, datetime, GM_Object, GM_Envelope, TM_Object, NoneType
]

OUTPUT_FIELDS = {
    bool: models.BooleanField(),
    str: models.CharField(),
    int: models.IntegerField(),
    date: models.DateField(),
    datetime: models.DateTimeField(),
    float: models.FloatField(),
    D: models.DecimalField(),
}


class BinaryOperatorType(TagNameEnum):
    """FES 1.0 Arithmetic operators.

    This are no longer part of the FES 2.0 spec, but clients (like QGis)
    still assume the server supports these. Hence these need to be included.
    """

    Add = operator.add
    Sub = operator.sub
    Mul = operator.mul
    Div = operator.truediv


class Expression(BaseNode):
    """Abstract base class, as defined by FES spec."""

    xml_ns = FES20

    def build_lhs(self, compiler) -> str:
        """Get the expression as the left-hand-side of the equation.

        This typically returns the expression as a 'field name' which can be
        used in the Django QuerySet.filter(name=...) syntax. When the
        expression is actually a Function/Literal, this should generate the
        name using a queryset annotation.
        """
        value = _make_combinable(self.build_rhs(compiler))
        return compiler.add_annotation(value)

    def build_rhs(self, compiler) -> RhsTypes:
        """Get the expression as the right-hand-side of the equation.

        Typically, this can return the exact value.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.build_rhs()")


@dataclass
@tag_registry.register("Literal")
class Literal(Expression):
    """The <fes:Literal> element that holds a literal value"""

    # The XSD definition even defines a sequence of xsd:any as possible member!
    raw_value: Union[NoneType, str, GM_Object, GM_Envelope, TM_Object]
    raw_type: Optional[str] = None

    def __str__(self):
        return self.value

    @cached_property
    def value(self) -> ParsedValue:  # officially <xsd:any>
        """Access the value of the element, casted to the appropriate data type."""
        if not isinstance(self.raw_value, str):
            return self.raw_value  # GML element or None
        elif self.type:
            # Cast the value based on the given xsd:QName
            return self.type.to_python(self.raw_value)
        else:
            # Make sure gt / datetime comparisons work out of the box.
            return auto_cast(self.raw_value)

    @cached_property
    def type(self) -> Optional[XsdTypes]:
        if not self.raw_type:
            return None

        xmlns, localname = split_xml_name(self.raw_type)
        if xmlns == "gml":
            return XsdTypes(self.raw_type)
        else:
            # No idea what XMLSchema was prefixed as (could be ns0 instead of xs:)
            return XsdTypes(localname)

    @classmethod
    @expect_tag(FES20, "Literal")
    def from_xml(cls, element: Element):
        children = len(element)
        if not children:
            # Common case: value is raw text
            raw_value = element.text
        elif children == 1 and is_gml_element(element[0]):
            # Possible: a <gml:Envelope> element to compare something against.
            raw_value = parse_gml_node(element[0])
        else:
            raise ExternalParsingError(
                f"Unsupported child element for <Literal> element: {element[0].tag}."
            )

        return cls(raw_value=raw_value, raw_type=element.get("type"))

    def build_lhs(self, compiler) -> str:
        """Alias the value when it's used in the left-hand-side.

        By aliasing the value using an annotation,
        it can be queried like a regular field name.
        """
        return compiler.add_annotation(
            Value(self.value, output_field=self.get_output_field())
        )

    def get_output_field(self):
        # When the value is used a left-hand-side, Django needs to know the output type.
        return OUTPUT_FIELDS.get(type(self.value))

    def build_rhs(self, compiler) -> Union[Combinable, Q, ParsedValue]:
        """Return the value when it's used in the right-hand-side"""
        return self.value

    def bind_type(self, type: XsdTypes):
        """Assign the expected type that this literal is compared against"""
        if not self.raw_type:
            self.__dict__["type"] = type
            self.__dict__.pop("value", None)  # reset cached_property


@dataclass
@tag_registry.register("ValueReference")
@tag_registry.register("PropertyName")  # FES 1.0 name, some clients still use this.
class ValueReference(Expression):
    """The <fes:ValueReference> element that holds an XPath string.
    In the fes XSD, this is declared as a subclass of xsd:string.

    The old WFS1/FES1 "PropertyName" is allowed as an alias.
    Various clients still send this, and mapserver/geoserver support this.
    """

    xpath: str

    def __str__(self):
        return self.xpath

    @classmethod
    @expect_tag(FES20, "ValueReference", "PropertyName", leaf=True)
    def from_xml(cls, element: Element):
        return cls(xpath=element.text)

    def build_lhs(self, compiler) -> str:
        """Optimized LHS: there is no need to alias a field lookup through an annotation."""
        match = self.parse_xpath(compiler.feature_type)
        return match.build_lhs(compiler)

    def build_rhs(self, compiler) -> RhsTypes:
        """Return the value as F-expression"""
        match = self.parse_xpath(compiler.feature_type)
        return match.build_rhs(compiler)

    def parse_xpath(self, feature_type=None) -> ORMPath:
        """Convert the XPath into a the required ORM query elements."""
        if feature_type is not None:
            # Can resolve against XSD paths, find the correct DB field name
            return feature_type.resolve_element(self.xpath)
        else:
            # Only used by unit testing (when feature_type is not given).
            parts = [word.strip() for word in self.xpath.split("/")]
            return ORMPath(orm_path="__".join(parts), orm_filters=None)

    @cached_property
    def element_name(self):
        """Tell which element this reference points to."""
        try:
            pos = self.xpath.rindex("/")
        except ValueError:
            return self.xpath
        else:
            return self.xpath[pos + 1 :]


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
            name=get_attribute(element, "name"),
            arguments=[Expression.from_child_xml(child) for child in element],
        )

    def build_rhs(self, compiler) -> RhsTypes:
        """Build the SQL function object"""
        db_function = function_registry.resolve_function(self.name)
        args = [arg.build_rhs(compiler) for arg in self.arguments]
        return db_function.build_query(*args)


@dataclass
@tag_registry.register_names(BinaryOperatorType)
class BinaryOperator(Expression):
    """Support for FES 1.0 arithmetic operators.

    This are no longer part of the FES 2.0 spec, but clients (like QGis)
    still assume the server supports these. Hence these need to be included.
    """

    _operatorType: BinaryOperatorType
    expression: Tuple[Expression, Expression]

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            _operatorType=BinaryOperatorType.from_xml(element),
            expression=(
                Expression.from_child_xml(element[0]),
                Expression.from_child_xml(element[1]),
            ),
        )

    def build_rhs(self, compiler) -> RhsTypes:
        value1 = _make_combinable(self.expression[0].build_rhs(compiler))
        value2 = _make_combinable(self.expression[1].build_rhs(compiler))
        return self._operatorType.value(value1, value2)


def _make_combinable(value) -> Union[Combinable, Q]:
    """Make sure the scalar value is wrapped inside a compilable object"""
    if isinstance(value, (Combinable, Q)):
        return value
    else:
        # e.g. str, or GEOSGeometry
        return Value(value, output_field=OUTPUT_FIELDS.get(type(value)))
