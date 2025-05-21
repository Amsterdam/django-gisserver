"""These classes map to the FES 2.0 specification for expressions.
The class names are identical to those in the FES spec.

Inheritance structure:

* :class:`Expression`

 * :class:`Function` for ``<fes:Function>``.
 * :class:`Literal` for ``<fes:Literal>``.
 * :class:`ValueReference` for ``<fes:ValueReference>``.
 * :class:`BinaryOperator` for FES 1.0 compatibility.

The :class:`BinaryOperator` is included as expression
to handle FES 1.0 :class:`BinaryOperatorType` arithmetic tags:
``<fes:Add>``, ``<fes:Sub>``, ``<fes:Mul>``, ``<fes:Div>``.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal as D
from functools import cached_property
from typing import Union

from django.contrib.gis import geos
from django.contrib.gis.db import models as gis_models
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Value
from django.db.models.expressions import Combinable

from gisserver.exceptions import ExternalParsingError
from gisserver.extensions.functions import function_registry
from gisserver.parsers.ast import (
    AstNode,
    TagNameEnum,
    expect_no_children,
    expect_tag,
    tag_registry,
)
from gisserver.parsers.gml import (
    GM_Envelope,
    GM_Object,
    TM_Object,
    is_gml_element,
    parse_gml_node,
)
from gisserver.parsers.query import RhsTypes
from gisserver.parsers.values import auto_cast
from gisserver.parsers.xml import NSElement, parse_qname, xmlns
from gisserver.types import XPathMatch, XsdTypes

NoneType = type(None)
ParsedValue = Union[int, str, date, D, datetime, GM_Object, GM_Envelope, TM_Object, NoneType]

OUTPUT_FIELDS = {
    bool: models.BooleanField(),
    str: models.CharField(),
    int: models.IntegerField(),
    date: models.DateField(),
    datetime: models.DateTimeField(),
    float: models.FloatField(),
    D: models.DecimalField(),
    geos.GEOSGeometry: gis_models.GeometryField(),
    geos.Point: gis_models.PointField(),
    geos.LineString: gis_models.LineStringField(),
    geos.LinearRing: gis_models.LineStringField(),
    geos.Polygon: gis_models.PolygonField(),
    geos.MultiPoint: gis_models.MultiPointField(),
    geos.MultiPolygon: gis_models.MultiPolygonField(),
    geos.MultiLineString: gis_models.MultiLineStringField(),
    geos.GeometryCollection: gis_models.GeometryCollectionField(),
}


class BinaryOperatorType(TagNameEnum):
    """FES 1.0 Arithmetic operators.

    These are no longer part of the FES 2.0 spec, but clients (like QGis)
    still assume the server supports these. Hence, these need to be included.
    """

    Add = operator.add
    Sub = operator.sub
    Mul = operator.mul
    Div = operator.truediv


class Expression(AstNode):
    """Abstract base class, as defined by FES spec.

    The FES spec defines the following subclasses:

    * :class:`ValueReference` (pointing to a field name)
    * :class:`Literal` (a scalar value)
    * :class:`Function` (a transformation for a value/field)

    When code uses ``Expression.child_from_xml(element)``, the AST logic will
    initialize the correct subclass for those elements.
    """

    xml_ns = xmlns.fes20

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


@dataclass(repr=False)
@tag_registry.register("Literal")
class Literal(Expression):
    """The ``<fes:Literal>`` element that holds a literal value.

    This can be a string value, possibly annotated with a type::

        <fes:Literal type="xs:boolean">true</fes:Literal>

    Following the spec, the value may also contain a complete geometry::

        <fes:Literal>
            <gml:Envelope xmlns:gml="http://www.opengis.net/gml/3.2" srsName="urn:ogc:def:crs:EPSG::4326">
                <gml:lowerCorner>5.7 53.1</gml:lowerCorner>
                <gml:upperCorner>6.1 53.5</gml:upperCorner>
            </gml:Envelope>
        </fes:Literal>
    """

    # The XSD definition even defines a sequence of xsd:any as possible member!
    raw_value: NoneType | str | GM_Object | GM_Envelope | TM_Object
    raw_type: str | None = None

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"Literal({self.raw_value!r}, raw_type={self.raw_type!r}, type={self.type!r})"

    @cached_property
    def value(self) -> ParsedValue:  # officially <xsd:any>
        """Access the value of the element, cast to the appropriate data type.
        :raises ExternalParsingError: When the value can't be converted to the proper type.
        """
        if not isinstance(self.raw_value, str):
            return self.raw_value  # GML element or None
        elif self.type:
            # Cast the value based on the given xsd:QName
            return self.type.to_python(self.raw_value)
        else:
            # Make sure gt / datetime comparisons work out of the box.
            return auto_cast(self.raw_value)

    @cached_property
    def type(self) -> XsdTypes | None:
        """Tell which datatype the literal holds.
        This returns the type="..." value of the element.
        """
        if not self.raw_type:
            return None

        # The raw type is already translated into a fully qualified XML name,
        # which also allows defining types as "ns0:string", "xs:string" or "xsd:string".
        # These are directly matched to the XsdTypes enum value.
        return XsdTypes(self.raw_type)

    @classmethod
    @expect_tag(xmlns.fes20, "Literal")
    def from_xml(cls, element: NSElement):
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

        return cls(
            raw_value=raw_value,
            raw_type=parse_qname(element.attrib.get("type"), element.ns_aliases),
        )

    def build_lhs(self, compiler) -> str:
        """Alias the value when it's used in the left-hand-side.

        By aliasing the value using an annotation,
        it can be queried like a regular field name.
        """
        return compiler.add_annotation(Value(self.value, output_field=self.get_output_field()))

    def get_output_field(self):
        # When the value is used a left-hand-side, Django needs to know the output type.
        return OUTPUT_FIELDS.get(type(self.value))

    def build_rhs(self, compiler) -> Combinable | Q | ParsedValue:
        """Return the value when it's used in the right-hand-side"""
        return self.value

    def bind_type(self, type: XsdTypes):
        """Assign the expected type that this literal is compared against"""
        if not self.raw_type:
            self.__dict__["type"] = type
            self.__dict__.pop("value", None)  # reset cached_property


@dataclass(repr=False)
@tag_registry.register("ValueReference")
@tag_registry.register("PropertyName", hidden=True)  # FES 1.0 name that old clients still use.
class ValueReference(Expression):
    """The ``<fes:ValueReference>`` element that holds an XPath string.
    In the fes XSD, this is declared as a subclass of xsd:string.

    This parses the syntax like::

        <fes:ValueReference>field-name</fes:ValueReference>
        <fes:ValueReference>path/to/field-name</fes:ValueReference>
        <fes:ValueReference>collection[@attr=value]/field-name</fes:ValueReference>

    The old WFS1/FES1 "PropertyName" is allowed as an alias.
    Various clients still send this, and mapserver/geoserver support this.
    """

    #: The XPath value
    xpath: str
    #: The known namespaces aliases at this point in the XML tree
    xpath_ns_aliases: dict[str, str] | None = field(compare=False, default=None)

    def __str__(self):
        return self.xpath

    def __repr__(self):
        return f"ValueReference({self.xpath!r})"

    @classmethod
    @expect_tag(xmlns.fes20, "ValueReference", "PropertyName")
    @expect_no_children
    def from_xml(cls, element: NSElement):
        return cls(xpath=element.text, xpath_ns_aliases=element.ns_aliases)

    def build_lhs(self, compiler) -> str:
        """Use the field name in a left-hand-side expression."""
        # Optimized from base class: fields don't need an alias lookup through annotations.
        match = self.parse_xpath(compiler.feature_types)
        return match.build_lhs(compiler)

    def build_rhs(self, compiler) -> RhsTypes:
        """Use the field name in a right-hand expression.
        This generates an F-expression for the ORM."""
        match = self.parse_xpath(compiler.feature_types)
        return match.build_rhs(compiler)

    def parse_xpath(self, feature_types: list) -> XPathMatch:
        """Convert the XPath into the required ORM query elements."""
        return feature_types[0].resolve_element(self.xpath, self.xpath_ns_aliases)


@dataclass
@tag_registry.register("Function")
class Function(Expression):
    """The ``<fes:Function name="...">`` element.

    This parses the syntax such as::

        <fes:Function name="Add">
            <fes:ValueReference>field-name</fes:ValueReference>
            <fes:Literal>2</fes:Literal>
        </fes:Function>

    Each argument of the function can be another :class:`Expression`,
    such as a :class:`Function`, :class:`ValueReference` or :class:`Literal`.
    """

    name: str  # scoped name
    arguments: list[Expression]  # xsd:element ref="fes20:expression"

    @classmethod
    @expect_tag(xmlns.fes20, "Function")
    def from_xml(cls, element: NSElement):
        return cls(
            name=element.get_str_attribute("name"),
            arguments=[Expression.child_from_xml(child) for child in element],
        )

    def build_rhs(self, compiler) -> models.Func:
        """Build the SQL function object"""
        db_function = function_registry.resolve_function(self.name)
        args = [arg.build_rhs(compiler) for arg in self.arguments]
        return db_function.build_query(*args)


@dataclass
@tag_registry.register(BinaryOperatorType)
class BinaryOperator(Expression):
    """Support for FES 1.0 arithmetic operators.

    This parses a syntax like::

        <fes:Add>
            <fes:ValueReference>field-name</fes:ValueReference>
            <fes:Literal>2</fes:Literal>
        </fes:Add>

    The operator can be a ``<fes:Add>``, ``<fes:Sub>``, ``<fes:Mul>``, ``<fes:Div>``.

    These are no longer part of the FES 2.0 spec, but clients (like QGis)
    still assume the server use these. Hence, these need to be included.
    """

    _operatorType: BinaryOperatorType
    expression: tuple[Expression, Expression]

    @classmethod
    def from_xml(cls, element: NSElement):
        return cls(
            _operatorType=BinaryOperatorType.from_xml(element),
            expression=(
                Expression.child_from_xml(element[0]),
                Expression.child_from_xml(element[1]),
            ),
        )

    def build_rhs(self, compiler) -> RhsTypes:
        self.validate_arithmetic(compiler, self.expression[0], self.expression[1])
        value1 = self.expression[0].build_rhs(compiler)
        value2 = self.expression[1].build_rhs(compiler)

        # Func() + 2 or 2 + Func() are automatically handled,
        # but Q(..) + 2 or 2 + Q(..) aren't.
        # When both are values, a direct calculation takes place in Python.
        if isinstance(value1, Q):
            value2 = _make_combinable(value2)
        if isinstance(value2, Q):
            value1 = _make_combinable(value1)

        try:
            # This calls somthing like: operator.add(F("field"), 2) or operator.add(1, 2)
            return self._operatorType.value(value1, value2)
        except (TypeError, ValueError, ArithmeticError) as e:
            raise ValidationError(
                f"Invalid data for the 'fes:{self._operatorType.name}' element: {value1} {value2}"
            ) from e

    def validate_arithmetic(self, compiler, lhs: Expression, rhs: Expression):
        """Check whether values support arithmetic operators."""
        if isinstance(lhs, Literal) and isinstance(rhs, ValueReference):
            lhs, rhs = rhs, lhs

        if isinstance(lhs, ValueReference):
            xsd_element = lhs.parse_xpath(compiler.feature_types).child
            if isinstance(rhs, Literal):
                # Since the element is resolved, inform the Literal how to parse the value.
                # This avoids various validation errors along the path.
                rhs.bind_type(xsd_element.type)

                # Validate the expressions against each other
                # This raises an ValidationError when values can't be converted
                xsd_element.to_python(rhs.raw_value)

        return None


def _make_combinable(value) -> Combinable | Q:
    """Make sure the scalar value is wrapped inside a compilable object"""
    if isinstance(value, (Combinable, Q)):
        return value
    else:
        # e.g. str, or GEOSGeometry
        return Value(value, output_field=OUTPUT_FIELDS.get(type(value)))
