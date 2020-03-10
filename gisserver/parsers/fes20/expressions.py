"""These classes map to the FES 2.0 specification for expressions.
The class names are identical to those in the FES spec.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal as D
from typing import Any, List, Optional, Tuple, Union
from xml.etree.ElementTree import Element

from django.contrib.gis.geos import GEOSGeometry
from django.db.models import F, Func, Q, Value
from django.db.models.expressions import Combinable

from gisserver.parsers.base import FES20, BaseNode, tag_registry
from gisserver.parsers.fes20.functions import function_registry
from gisserver.parsers.fes20.query import FesQuery
from gisserver.parsers.gml import GM_Object
from gisserver.parsers.utils import auto_cast, expect_tag, xsd_cast

NoneType = type(None)
RE_NON_NAME = re.compile(r"[^a-zA-Z0-9_/]")

RhsTypes = Union[
    Combinable, Func, Q, GEOSGeometry, bool, int, str, date, datetime, tuple
]


# Define interface for any class that has "build_rhs()"
try:
    from typing import Protocol
except ImportError:
    HasBuildRhs = Any  # Python 3.7 and below
else:

    class HasBuildRhs(Protocol):
        def build_rhs(self, fesquery) -> RhsTypes:
            ...


class Expression(BaseNode):
    """Abstract base class, as defined by FES spec."""

    xml_ns = FES20

    def build_lhs(self, fesquery) -> str:
        """Get the expression as the left-hand-side of the equation.

        This typically returns the expression as a 'field name' which can be
        used in the Django QuerySet.filter(name=...) syntax. When the
        expression is actually a Function/Literal, this should generate the
        name using a queryset annotation.
        """
        value = self.build_rhs(fesquery)
        if not isinstance(value, (Combinable, Q)):
            value = Value(value)  # e.g. str, or GEOSGeometry

        return fesquery.add_annotation(value)

    def build_rhs(self, fesquery) -> RhsTypes:
        """Get the expression as the right-hand-side of the equation.

        Typically, this can return the exact value.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.build_rhs()")

    def build_compare(self, fesquery: FesQuery, lookup, rhs) -> Q:
        """Use the value in comparison with some other expression.

        This calls build_lhs() and build_rhs() on the expressions.
        """
        lhs = self.build_lhs(fesquery)

        if isinstance(rhs, (Expression, GM_Object)):
            rhs = rhs.build_rhs(fesquery)

        result = Q(**{f"{lhs}__{lookup}": rhs})
        return fesquery.apply_extra_lookups(result)

    def build_compare_between(
        self, fesquery: FesQuery, lookup, rhs: Tuple[HasBuildRhs, HasBuildRhs]
    ) -> Q:
        """Use the value in comparison with 2 other values (e.g. between query)"""
        lhs = self.build_lhs(fesquery)
        result = Q(
            **{
                f"{lhs}__{lookup}": (
                    rhs[0].build_rhs(fesquery),
                    rhs[1].build_rhs(fesquery),
                )
            }
        )
        return fesquery.apply_extra_lookups(result)


@dataclass
@tag_registry.register("Literal")
class Literal(Expression):
    """The <fes:Literal> element that holds a literal value"""

    value: Union[int, str, date, D, datetime, NoneType]  # officially <xsd:any>
    type: Optional[str] = None

    def __str__(self):
        return self.value

    @classmethod
    @expect_tag(FES20, "Literal")
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

    def build_lhs(self, fesquery) -> str:
        """Alias the value when it's used in the left-hand-side.

        By aliasing the value using an annotation,
        it can be queried like a regular field name.
        """
        return fesquery.add_annotation(Value(self.value))

    def build_rhs(self, fesquery) -> Union[Combinable, Q, str]:
        """Return the value when it's used in the right-hand-side"""
        return self.value


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

    def build_lhs(self, fesquery) -> str:
        """Optimized LHS: there is no need to alias a field lookup through an annotation."""
        field, extra_q = self.parse_xpath()
        if extra_q:
            fesquery.add_extra_lookup(extra_q)
        return field

    def build_rhs(self, fesquery) -> RhsTypes:
        """Return the value as F-expression"""
        return F(self.build_lhs(fesquery))

    def parse_xpath(self) -> Tuple[str, Optional[Q]]:
        """Return the value when it's used as left-hand side expression"""
        parts = [word.strip() for word in self.xpath.split("/")]
        orm_field = "__".join(parts)

        if RE_NON_NAME.match(orm_field):
            # If there is an element[@attr=...]/field tag,
            # the get_filter() part should return a Q() object.
            raise NotImplementedError(
                f"Complex XPath queries are not supported yet: {self.xpath}"
            )

        return orm_field, None


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

    def build_rhs(self, fesquery) -> RhsTypes:
        """Build the SQL function object"""
        db_function = function_registry.resolve_function(self.name)
        args = [arg.build_rhs(fesquery) for arg in self.arguments]
        return db_function(*args)
