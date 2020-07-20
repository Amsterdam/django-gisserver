"""These classes map to the FES 2.0 specification for operators.
The class names and attributes are identical to those in the FES spec.
"""
from itertools import groupby

import operator
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from functools import reduce
from typing import Any, Dict, List, Optional, Tuple, Union
from xml.etree.ElementTree import Element

from django.contrib.gis import measure
from django.db.models import Q
from django.utils.functional import cached_property

from gisserver.exceptions import ExternalParsingError, OperationProcessingFailed
from gisserver.parsers import gml
from gisserver.parsers.base import BaseNode, TagNameEnum, tag_registry
from gisserver.parsers.utils import expect_tag, get_attribute, get_child
from gisserver.types import FES20
from .identifiers import Id
from .expressions import Expression, Literal, RhsTypes, ValueReference
from .query import CompiledQuery

SpatialDescription = Union[gml.GM_Object, gml.GM_Envelope, ValueReference]
TemporalOperand = Union[gml.TM_Object, ValueReference]


# Define interface for any class that has "build_rhs()"
try:
    from typing import Protocol
except ImportError:
    HasBuildRhs = Any  # Python 3.7 and below
else:

    class HasBuildRhs(Protocol):
        def build_rhs(self, compiler) -> RhsTypes:
            ...


class MatchAction(Enum):
    """Values for the 'matchAction' attribute of the BinaryComparisonOperator."""

    All = "All"
    Any = "Any"
    One = "One"

    def __repr__(self):
        # Make repr(filter) easier to copy-paste
        return f"{self.__class__.__name__}.{self.name}"


class BinaryComparisonName(TagNameEnum):
    """XML tag names for value comparisons.
    Values are the used field lookup.
    """

    PropertyIsEqualTo = "exact"
    PropertyIsNotEqualTo = "fes_notequal"  # custom FesNotEqualTo lookup
    PropertyIsLessThan = "lt"
    PropertyIsGreaterThan = "gt"
    PropertyIsLessThanOrEqualTo = "lte"
    PropertyIsGreaterThanOrEqualTo = "gte"


class DistanceOperatorName(TagNameEnum):
    """XML tag names for distance operators"""

    Beyond = "fes_not_dwithin"  # using __distance_gt=.. would be slower.
    DWithin = "dwithin"  # ST_DWithin uses indices, distance_lte does not.


class SpatialOperatorName(TagNameEnum):
    """XML tag names for geometry operators"""

    # (A Within B) implies that (B Contains A)

    # BBOX can either be implemented using bboverlaps (more efficient), or the
    # more correct "intersects" option (e.g. a line near the box would match otherwise).
    BBOX = "intersects"  # ISO version: "NOT DISJOINT"
    Equals = "equals"  # Test whether t geometries are topologically equal
    Disjoint = "disjoint"  # Tests whether two geometries are disjoint (do not interact)
    Intersects = "intersects"  # Tests whether two geometries intersect
    Touches = "touches"  # Tests whether two geometries touch
    Crosses = "crosses"  # Tests whether two geometries cross
    Within = "within"  # Tests whether a geometry is within another one
    Contains = "contains"  # Tests whether a geometry contains another one
    Overlaps = "overlaps"  # Test whether two geometries overlap


class TemporalOperatorName(TagNameEnum):
    """XML tag names for datetime operators."""

    After = "after"
    Before = "before"
    Begins = "begins"
    BegunBy = "begunby"
    TContains = "tcontains"
    TEquals = "tequals"
    TOverlaps = "toverlaps"
    During = "during"
    Meets = "meets"
    OverlappedBy = "overlappedby"
    MetBy = "metby"
    EndedBy = "endedby"
    AnyInteracts = "anyinteracts"


class BinaryLogicType(TagNameEnum):
    """XML tag names for the BinaryLogicOperator."""

    And = operator.and_
    Or = operator.or_


class UnaryLogicType(TagNameEnum):
    """XML tag names for the UnaryLogicOperator."""

    Not = operator.inv


@dataclass
class Measure(BaseNode):
    """The <fes:Distance uom="...> element."""

    xml_ns = FES20

    value: Decimal
    uom: str  # Unit of measurement, Union[fes20:UomSymbol fes20:UomURI]

    @classmethod
    @expect_tag(FES20, "Distance")
    def from_xml(cls, element: Element):
        return cls(value=Decimal(element.text), uom=get_attribute(element, "uom"))

    def build_rhs(self, compiler) -> measure.Distance:
        return measure.Distance(default_unit=self.uom, **{self.uom: self.value})


class Operator(BaseNode):
    """Abstract base class, as defined by FES spec."""

    xml_ns = FES20

    def build_query(self, compiler: CompiledQuery) -> Optional[Q]:
        raise NotImplementedError(
            f"Using {self.__class__.__name__} is not supported yet."
        )


@dataclass
class IdOperator(Operator):
    """List of ResourceId objects"""

    id: List[Id]

    @property
    def type_names(self) -> List[str]:
        """Provide a list of all type names accessed by this operator"""
        return [
            type_name for type_name in self.grouped_ids.keys() if type_name is not None
        ]

    @cached_property
    def grouped_ids(self) -> Dict[str, List[Id]]:
        # For itertools.groupby(), items have to be sorted first.
        ids = sorted(self.id, key=operator.attrgetter("rid"))
        return {
            type_name: list(items)
            for type_name, items in groupby(ids, key=operator.attrgetter("type_name"))
        }

    def build_query(self, compiler):
        """Generate the ID lookup query.

        As these identifiers also reference the type name, no Q-object is
        returned. The lookups are directly added to the fes query object.
        """
        # When ResourceId has no type_name associated, this means that the
        # parsing was invalid. Instead of raising an error, empty results are returned.
        if len(self.grouped_ids) == 1 and self.grouped_ids.get(None):
            compiler.mark_empty()
            return

        for type_name, items in self.grouped_ids.items():
            ids_subset = reduce(
                operator.or_, [id.build_query(compiler=None) for id in items]
            )
            compiler.add_lookups(ids_subset, type_name=type_name)


class NonIdOperator(Operator):
    """Abstract base class, as defined by FES spec."""

    _source = None
    allow_geometries = False

    def build_compare(
        self,
        compiler: CompiledQuery,
        lhs: Expression,
        lookup: str,
        rhs: Union[Expression, RhsTypes],
    ) -> Q:
        """Use the value in comparison with some other expression.

        This calls build_lhs() and build_rhs() on the expressions.
        """
        # lhs and rhs are allowed to be reversed. However, the SQL compiler
        # works much simpler when Django can predict the actual data type.
        if isinstance(lhs, Literal) and isinstance(rhs, ValueReference):
            lhs, rhs = rhs, lhs

        if compiler.feature_type is not None:
            self.validate_comparison(compiler, lhs, lookup, rhs)

        lhs = lhs.build_lhs(compiler)

        if isinstance(rhs, (Expression, gml.GM_Object)):
            rhs = rhs.build_rhs(compiler)

        result = Q(**{f"{lhs}__{lookup}": rhs})
        return compiler.apply_extra_lookups(result)

    def validate_comparison(
        self, compiler, lhs: Expression, lookup: str, rhs: Union[Expression, RhsTypes]
    ):
        """Validate whether a given comparison is even possible.
        Where needed, the lhs/rhs are already ordered in a logical sequence.
        """
        if isinstance(lhs, ValueReference):
            xsd_element = compiler.feature_type.resolve_element(lhs.xpath).child
            tag = self._source if self._source is not None else None

            # e.g. deny <PropertyIsLessThanOrEqualTo> against <gml:boundedBy>
            if xsd_element.is_geometry and not self.allow_geometries:
                raise OperationProcessingFailed(
                    "filter",
                    f"Operator '{tag}' does not support comparing"
                    f" geometry properties: '{xsd_element.xml_name}'.",
                    status_code=400,  # not HTTP 500 here. Spec allows both.
                )

            if isinstance(rhs, Literal):
                # Since the element is resolved, inform the Literal how to parse the value.
                # This avoids various validation errors along the path.
                rhs.bind_type(xsd_element.type)

                # When a common case of value comparison is done, the inputs
                # can be validated before the ORM query is constructed.
                xsd_element.validate_comparison(rhs.raw_value, lookup=lookup, tag=tag)

    def build_compare_between(
        self,
        compiler: CompiledQuery,
        lhs: Expression,
        lookup: str,
        rhs: Tuple[HasBuildRhs, HasBuildRhs],
    ) -> Q:
        """Use the value in comparison with 2 other values (e.g. between query)"""
        if compiler.feature_type is not None:
            self.validate_comparison(compiler, lhs, lookup, rhs[0])
            self.validate_comparison(compiler, lhs, lookup, rhs[1])

        field_name = lhs.build_lhs(compiler)
        result = Q(
            **{
                f"{field_name}__{lookup}": (
                    rhs[0].build_rhs(compiler),
                    rhs[1].build_rhs(compiler),
                )
            }
        )
        return compiler.apply_extra_lookups(result)


class SpatialOperator(NonIdOperator):
    """Abstract base class, as defined by FES spec."""


@dataclass
@tag_registry.register_names(DistanceOperatorName)  # <Beyond>, <DWithin>
class DistanceOperator(SpatialOperator):
    """Comparing the distance to a geometry."""

    allow_geometries = True  # override static attribute

    valueReference: ValueReference
    operatorType: DistanceOperatorName
    geometry: gml.GM_Object
    distance: Measure
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        geometries = gml.find_gml_nodes(element)
        if not geometries:
            raise ExternalParsingError(f"Missing gml element in <{element.tag}>")
        elif len(geometries) > 1:
            raise ExternalParsingError(
                f"Multiple gml elements found in <{element.tag}>"
            )

        return cls(
            valueReference=ValueReference.from_xml(
                get_child(element, FES20, "ValueReference")
            ),
            operatorType=DistanceOperatorName.from_xml(element),
            geometry=gml.parse_gml_node(geometries[0]),
            distance=Measure.from_xml(get_child(element, FES20, "Distance")),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        return self.build_compare_between(
            compiler,
            lhs=self.valueReference,
            lookup=self.operatorType.value,
            rhs=(self.geometry, self.distance),
        )


@dataclass
@tag_registry.register_names(SpatialOperatorName)  # <BBOX>, <Equals>, ...
class BinarySpatialOperator(SpatialOperator):
    """A comparison of geometries using 2 values, e.g. A Within B."""

    allow_geometries = True  # override static attribute

    operatorType: SpatialOperatorName
    operand1: Optional[ValueReference]
    operand2: SpatialDescription
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        operator_type = SpatialOperatorName.from_xml(element)
        if operator_type is SpatialOperatorName.BBOX and len(element) == 1:
            # For BBOX, the geometry operator is optional
            ref = None
            geo = element[0]
        else:
            if len(element) != 2:
                raise ExternalParsingError(f"{element.tag} should have 2 operators")
            ref, geo = list(element)

        return cls(
            operatorType=operator_type,
            operand1=ValueReference.from_xml(ref) if ref is not None else None,
            operand2=tag_registry.from_child_xml(
                geo, allowed_types=SpatialDescription.__args__,  # get_args() in 3.8
            ),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        operant1 = self.operand1
        if operant1 is None:
            operant1 = ValueReference(xpath=compiler.feature_type.geometry_field_name)

        return self.build_compare(
            compiler, lhs=operant1, lookup=self.operatorType.value, rhs=self.operand2,
        )


@dataclass
@tag_registry.register_names(TemporalOperatorName)  # <After>, <Before>, ...
class TemporalOperator(NonIdOperator):
    """Comparisons with dates"""

    operatorType: TemporalOperatorName
    operand1: ValueReference
    operand2: TemporalOperand
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            operatorType=TemporalOperatorName.from_xml(element),
            operand1=ValueReference.from_xml(element[0]),
            operand2=tag_registry.from_child_xml(
                element[1], allowed_types=TemporalOperand.__args__,  # get_args() in 3.8
            ),
            _source=element.tag,
        )


class ComparisonOperator(NonIdOperator):
    """Base class for comparisons"""

    # Start counting fresh here, to collect the capabilities
    # that are listed in the <fes20:ComparisonOperators> node:
    xml_tags = []


@dataclass
@tag_registry.register_names(BinaryComparisonName)  # <PropertyIs...>
class BinaryComparisonOperator(ComparisonOperator):
    """A comparison between 2 values, e.g. A == B."""

    operatorType: BinaryComparisonName
    expression: Tuple[Expression, Expression]
    matchCase: bool = True
    matchAction: MatchAction = MatchAction.Any
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            operatorType=BinaryComparisonName.from_xml(element),
            expression=(
                Expression.from_child_xml(element[0]),
                Expression.from_child_xml(element[1]),
            ),
            matchCase=element.get("matchCase", True),
            matchAction=MatchAction(
                element.get("matchAction", default=MatchAction.Any)
            ),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        lhs, rhs = self.expression
        return self.build_compare(
            compiler, lhs=lhs, lookup=self.operatorType.value, rhs=rhs
        )


@dataclass
@tag_registry.register("PropertyIsBetween")
class BetweenComparisonOperator(ComparisonOperator):
    """Check whether a value is between two elements."""

    expression: Expression
    lowerBoundary: Expression
    upperBoundary: Expression
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        lower = get_child(element, FES20, "LowerBoundary")
        upper = get_child(element, FES20, "UpperBoundary")
        return cls(
            expression=Expression.from_child_xml(element[0]),
            lowerBoundary=Expression.from_child_xml(lower[0]),
            upperBoundary=Expression.from_child_xml(upper[0]),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        return self.build_compare_between(
            compiler,
            lhs=self.expression,
            lookup="range",
            rhs=(self.lowerBoundary, self.upperBoundary),
        )


@dataclass
@tag_registry.register("PropertyIsLike")
class LikeOperator(ComparisonOperator):
    """Perform wildcard matching."""

    expression: Tuple[Expression, Expression]
    wildCard: str
    singleChar: str
    escapeChar: str
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            expression=(
                Expression.from_child_xml(element[0]),
                Expression.from_child_xml(element[1]),
            ),
            wildCard=get_attribute(element, "wildCard"),
            singleChar=get_attribute(element, "singleChar"),
            escapeChar=get_attribute(element, "escapeChar"),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        lhs, rhs = self.expression
        if isinstance(rhs, Literal):
            value = str(rhs.value)  # value could be auto-casted to int.

            # Not using r"\" here as that is a syntax error.
            if self.escapeChar != "\\":
                value = value.replace("\\", "\\\\").replace(self.escapeChar, "\\")
            if self.wildCard != "%":
                value = value.replace("%", r"\%").replace(self.wildCard, "%")
            if self.singleChar != "_":
                value = value.replace("_", r"\_").replace(self.singleChar, "_")

            rhs = Literal(raw_value=value)
        else:
            raise NotImplementedError()

        # Use the FesLike lookup
        return self.build_compare(compiler, lhs=lhs, lookup="fes_like", rhs=rhs)


@dataclass
@tag_registry.register("PropertyIsNil")
class NilOperator(ComparisonOperator):
    """Check whether the value evaluates to null/None.
    If the WFS would return a property element with <tns:p xsi:nil='true'>, this returns true.
    """

    expression: Optional[Expression]
    nilReason: str
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            expression=Expression.from_child_xml(element[0]) if element else None,
            nilReason=element.get("nilReason"),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        # Any value that evaluates to None is returned as 'xs:nil' in our output.
        return self.build_compare(
            compiler, lhs=self.expression, lookup="isnull", rhs=True
        )


@dataclass
@tag_registry.register("PropertyIsNull")
class NullOperator(ComparisonOperator):
    """Check whether the property exists.
    If the WFS would not return the property element <tns:p>, this returns true.
    """

    expression: Expression
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            expression=Expression.from_child_xml(element[0]), _source=element.tag
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        # For now, the implementation is identical to PropertyIsNil.
        # According to the WFS spec, this should only be true when the element
        # is not returned at all (minOccurs=0).
        return self.build_compare(
            compiler, lhs=self.expression, lookup="isnull", rhs=True
        )


class LogicalOperator(NonIdOperator):
    """Base class for AND, OR, NOT comparisons"""


@dataclass
@tag_registry.register("And")
@tag_registry.register("Or")
class BinaryLogicOperator(LogicalOperator):
    """Apply an AND or OR operator"""

    operands: List[NonIdOperator]
    operatorType: BinaryLogicType
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            operands=[NonIdOperator.from_child_xml(child) for child in element],
            operatorType=BinaryLogicType.from_xml(element),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        """Apply the AND/OR operation to the Q-object"""
        values = [q.build_query(compiler) for q in self.operands]
        return reduce(self.operatorType.value, values)


@dataclass
@tag_registry.register("Not")
class UnaryLogicOperator(LogicalOperator):
    """Apply a NOT operator"""

    operands: NonIdOperator
    operatorType: UnaryLogicType
    _source: Optional[str] = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            operands=NonIdOperator.from_child_xml(element[0]),
            operatorType=UnaryLogicType.from_xml(element),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        """Apply the NOT operation to the Q-object"""
        return self.operatorType.value(self.operands.build_query(compiler))


class ExtensionOperator(NonIdOperator):
    """Base class for extensions to FES20"""
