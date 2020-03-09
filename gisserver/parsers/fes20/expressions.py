"""These classes map to the FES 2.0 specification for expressions.
The class names are identical to those in the FES spec.
"""
import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple, Union
from xml.etree.ElementTree import Element

from django.db.models import F, Func, Q, Value
from django.db.models.expressions import Combinable

from gisserver.parsers.base import BaseNode, FES20, tag_registry
from gisserver.parsers.fes20.functions import function_registry
from gisserver.parsers.fes20.query import FesQuery
from gisserver.parsers.gml import GM_Object
from gisserver.parsers.utils import expect_tag

NoneType = type(None)
RE_NON_NAME = re.compile(r"[^a-zA-Z0-9_/]")


class Expression(BaseNode):
    """Abstract base class, as defined by FES spec."""

    xml_ns = FES20

    def get_lhs(self, fesquery) -> str:
        """Get the expression as the left-hand-side of the equation.

        This returns the expression as a 'field name' which can be used in the
        Django QuerySet.filter(name=...) syntax. When the expresison is
        actually a Function/Literal, this would generate the name using a
        queryset annotation.
        """
        # By aliasing the value using an annotation,
        # it can be queried like a regular field name.
        return fesquery.add_annotation(
            self.build_operator_value(fesquery, is_rhs=False)
        )

    def build_operator_value(
        self, fesquery: FesQuery, is_rhs: bool
    ) -> Union[Combinable, Q]:
        raise NotImplementedError()

    def build_compare(self, fesquery: FesQuery, lookup, rhs) -> Q:
        """Use the value in comparison with some other expression."""
        lhs = self.get_lhs(fesquery)

        if isinstance(rhs, (Expression, GM_Object)):
            rhs = rhs.build_operator_value(fesquery, is_rhs=True)

        result = Q(**{f"{lhs}__{lookup}": rhs})
        return fesquery.combine_extra_lookups(result)

    def build_compare_between(
        self, fesquery: FesQuery, lookup, rhs: Tuple["Expression", "Expression"]
    ) -> Q:
        """Use the value in comparison with 2 other values (e.g. between query)"""
        lhs = self.get_lhs(fesquery)
        result = Q(
            **{
                f"{lhs}__{lookup}": (
                    rhs[0].build_operator_value(fesquery, is_rhs=True),
                    rhs[1].build_operator_value(fesquery, is_rhs=True),
                )
            }
        )
        return fesquery.combine_extra_lookups(result)


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

    def build_operator_value(self, fesquery, is_rhs: bool) -> Union[Combinable, Q]:
        if is_rhs:
            return self.value
        else:
            return Value(self.value)


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

    def build_operator_value(self, fesquery, is_rhs: bool) -> Union[Combinable, Q]:
        return F(self.get_lhs(fesquery))

    def get_lhs(self, fesquery) -> str:
        """Optimized LHS: there is no need to alias a field lookup through an annotation."""
        field, extra_q = self.parse_xpath()
        if extra_q:
            fesquery.add_extra_lookup(extra_q)
        return field

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

    def build_query(self, fesquery: FesQuery) -> Func:
        function = function_registry.resolve_function(self.name)
        args = [
            arg.build_operator_value(fesquery, is_rhs=True) for arg in self.arguments
        ]
        return function(*args)

    def build_operator_value(self, fesquery, is_rhs: bool) -> Union[Combinable, Q]:
        return self.build_query(fesquery)
