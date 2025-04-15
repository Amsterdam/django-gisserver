"""These classes map to the FES 2.0 specification for expressions.
The class names are identical to those in the FES spec.
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
from django.db import models
from django.db.models import Q, Value
from django.db.models.expressions import Combinable

from gisserver.exceptions import ExternalParsingError
from gisserver.extensions.functions import function_registry
from gisserver.parsers.ast import (
    BaseNode,
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
from gisserver.types import ORMPath, XsdTypes

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


class Expression(BaseNode):
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
    """The <fes:Literal> element that holds a literal value.

    This can be a string value, possibly annotated with a type::

        <fes:Literal type="xs:boolean">true</fes:Literal>

    Following the spec, the value may also contain a complete geometry:

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
        """Access the value of the element, cast to the appropriate data type."""
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
    """The <fes:ValueReference> element that holds an XPath string.
    In the fes XSD, this is declared as a subclass of xsd:string.

    The old WFS1/FES1 "PropertyName" is allowed as an alias.
    Various clients still send this, and mapserver/geoserver support this.
    """

    xpath: str
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
        """Optimized LHS: there is no need to alias a field lookup through an annotation."""
        match = self.parse_xpath(compiler.feature_types)
        return match.build_lhs(compiler)

    def build_rhs(self, compiler) -> RhsTypes:
        """Return the value as F-expression"""
        match = self.parse_xpath(compiler.feature_types)
        return match.build_rhs(compiler)

    def parse_xpath(self, feature_types: list) -> ORMPath:
        """Convert the XPath into the required ORM query elements."""
        if feature_types:
            # Can resolve against XSD paths, find the correct DB field name
            return feature_types[0].resolve_element(self.xpath, self.xpath_ns_aliases)
        else:
            # Only used by unit testing (when feature_type is not given).
            parts = [word.strip() for word in self.xpath.split("/")]
            return ORMPath(orm_path="__".join(parts), orm_filters=None)

    @cached_property
    def element_name(self):
        """Tell which element this reference points to."""
        return self.xpath.rpartition("/")[2]


@dataclass
@tag_registry.register("Function")
class Function(Expression):
    """The <fes:Function name="..."> element."""

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

    These are no longer part of the FES 2.0 spec, but clients (like QGis)
    still assume the server supports these. Hence, these need to be included.
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
        value1 = _make_combinable(self.expression[0].build_rhs(compiler))
        value2 = _make_combinable(self.expression[1].build_rhs(compiler))
        return self._operatorType.value(value1, value2)


def _make_combinable(value) -> Combinable | Q:
    """Make sure the scalar value is wrapped inside a compilable object"""
    if isinstance(value, (Combinable, Q)):
        return value
    else:
        # e.g. str, or GEOSGeometry
        return Value(value, output_field=OUTPUT_FIELDS.get(type(value)))
