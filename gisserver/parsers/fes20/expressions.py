"""These classes map to the FES 2.0 specification for expressions.
The class names are identical to those in the FES spec.
"""
import operator
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal as D
from django.utils.functional import cached_property
from typing import List, Optional, Tuple, Union
from xml.etree.ElementTree import Element

from django.contrib.gis.geos import GEOSGeometry
from django.db.models import F, Func, Q, Value
from django.db.models.expressions import Combinable

from gisserver.parsers.base import FES20, BaseNode, TagNameEnum, tag_registry
from gisserver.parsers.fes20.functions import function_registry
from gisserver.parsers.utils import (
    auto_cast,
    expect_tag,
    get_attribute,
    xsd_cast,
)

NoneType = type(None)
RE_NON_NAME = re.compile(r"[^a-zA-Z0-9_/]")

RhsTypes = Union[
    Combinable, Func, Q, GEOSGeometry, bool, int, str, date, datetime, tuple
]


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

    value: Union[int, str, date, D, datetime, NoneType]  # officially <xsd:any>
    type: Optional[str] = None

    def __str__(self):
        return self.value

    @classmethod
    @expect_tag(FES20, "Literal", leaf=True)
    def from_xml(cls, element: Element):
        type = element.get("type")
        value = element.text

        if type:
            # Cast the value based on the given xsd:QName
            value = xsd_cast(value, type)
        else:
            # Make sure gt / datetime comparisons work out of the box.
            value = auto_cast(value)

        return cls(value=value, type=type)

    def build_lhs(self, compiler) -> str:
        """Alias the value when it's used in the left-hand-side.

        By aliasing the value using an annotation,
        it can be queried like a regular field name.
        """
        return compiler.add_annotation(Value(self.value))

    def build_rhs(self, compiler) -> Union[Combinable, Q, str]:
        """Return the value when it's used in the right-hand-side"""
        return self.value


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
        field, extra_q = self.parse_xpath(compiler)
        if extra_q:
            compiler.add_extra_lookup(extra_q)
        return field

    def build_rhs(self, compiler) -> RhsTypes:
        """Return the value as F-expression"""
        return F(self.build_lhs(compiler))

    def parse_xpath(self, compiler) -> Tuple[str, Optional[Q]]:
        """Return the value when it's used as left-hand side expression"""
        if compiler.feature_type is not None:
            # Can resolve against XSD paths, find the correct DB field name
            path = compiler.feature_type.resolve_element_path(self.xpath)
            orm_field = "__".join(xsd_element.model_attribute for xsd_element in path)
        else:
            # Only used by unit testing (when feature_type is not given).
            parts = [word.strip() for word in self.xpath.split("/")]
            orm_field = "__".join(parts)

        if RE_NON_NAME.match(orm_field):
            # If there is an element[@attr=...]/field tag,
            # the get_filter() part should return a Q() object.
            raise NotImplementedError(
                f"Complex XPath queries are not supported yet: {self.xpath}"
            )

        return orm_field, None

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
        return Value(value)  # e.g. str, or GEOSGeometry
