"""These classes map to the FES 2.0 specification for operators.
The class names and attributes are identical to those in the FES spec.
"""
import operator
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Tuple, Union
from xml.etree.ElementTree import Element

from django.contrib.gis import measure

from gisserver.parsers import gml
from gisserver.parsers.base import FES20, BaseNode, TagNameEnum, tag_registry
from gisserver.parsers.utils import expect_tag, get_child
from .expressions import Expression, ValueReference

SpatialDescription = Union[gml.GM_Object, gml.GM_Envelope, ValueReference]
TemporalOperand = Union[gml.TM_Object, ValueReference]


class MatchAction(Enum):
    """Values for the 'matchAction' attribute of the BinaryComparisonOperator."""

    All = "All"
    Any = "Any"
    One = "One"

    def __repr__(self):
        # Make repr(filter) easier to copy-paste
        return f"{self.__class__.__name__}.{self.name}"


class BinaryComparisonName(TagNameEnum):
    """XML tag names for value comparisons"""

    PropertyIsEqualTo = operator.eq
    PropertyIsNotEqualTo = operator.ne
    PropertyIsLessThan = operator.lt
    PropertyIsGreaterThan = operator.gt
    PropertyIsLessThanOrEqualTo = operator.le
    PropertyIsGreaterThanOrEqualTo = operator.ge


class DistanceOperatorName(TagNameEnum):
    """XML tag names for distance operators"""

    Beyond = "Beyond"
    DWithin = "DWithin"


class SpatialOperatorName(TagNameEnum):
    """XML tag names for geometry operators"""

    BBOX = "BBOX"
    Equals = "Equals"
    Disjoint = "Disjoint"
    Intersects = "Intersects"
    Touches = "Touches"
    Crosses = "Crosses"
    Within = "Within"
    Contains = "Contains"
    Overlaps = "Overlaps"


class TemporalOperatorName(TagNameEnum):
    """XML tag names for datetime operators."""

    After = "After"
    Before = "Before"
    Begins = "Begins"
    BegunBy = "BegunBy"
    TContains = "TContains"
    TEquals = "TEquals"
    TOverlaps = "TOverlaps"
    During = "During"
    Meets = "Meets"
    OverlappedBy = "OverlappedBy"
    MetBy = "MetBy"
    EndedBy = "EndedBy"
    AnyInteracts = "AnyInteracts"


class BinaryLogicType(TagNameEnum):
    """XML tag names for the BinaryLogicOperator."""

    And = "And"
    Or = "Or"


class UnaryLogicType(TagNameEnum):
    """XML tag names for the UnaryLogicOperator."""

    Not = "Not"


@dataclass
class Measure(BaseNode):
    """The <fes:Distance uom="...> element."""

    xml_ns = FES20

    value: Decimal
    uom: str  # Unit of measurement, Union[fes20:UomSymbol fes20:UomURI]

    @classmethod
    @expect_tag(FES20, "Distance")
    def from_xml(cls, element: Element):
        return cls(value=Decimal(element.text), uom=element.attrib["uom"])

    def build_operator_value(self, fesquery, is_rhs: bool) -> measure.Distance:
        return measure.Distance(default_unit=self.uom, **{self.uom: self.value})


class Operator(BaseNode):
    """Abstract base class, as defined by FES spec."""

    xml_ns = FES20


class IdOperator(Operator):
    """Abstract base class, as defined by FES spec."""


class NonIdOperator(Operator):
    """Abstract base class, as defined by FES spec."""


class SpatialOperator(NonIdOperator):
    """Abstract base class, as defined by FES spec."""


@dataclass
@tag_registry.register_names(DistanceOperatorName)  # <Beyond>, <DWithin>
class DistanceOperator(SpatialOperator):
    """Comparing the distance to a geometry."""

    valueReference: ValueReference
    operatorType: DistanceOperatorName
    geometry: gml.GM_Object
    distance: Measure

    @classmethod
    def from_xml(cls, element: Element):
        geometries = gml.find_gml_nodes(element)
        if not geometries:
            raise ValueError(f"Missing gml element in <{element.tag}>")
        elif len(geometries) > 1:
            raise ValueError(f"Multiple gml elements found in <{element.tag}>")

        return cls(
            valueReference=ValueReference.from_xml(
                get_child(element, FES20, "ValueReference")
            ),
            operatorType=DistanceOperatorName.from_xml(element),
            geometry=gml.parse_gml_node(geometries[0]),
            distance=Measure.from_xml(get_child(element, FES20, "Distance")),
        )


@dataclass
@tag_registry.register_names(SpatialOperatorName)  # <BBOX>, <Equals>, ...
class BinarySpatialOperator(SpatialOperator):
    """A comparison of geometries using 2 values, e.g. A Within B."""

    operatorType: SpatialOperatorName
    operand1: Optional[ValueReference]
    operand2: SpatialDescription

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            operatorType=SpatialOperatorName.from_xml(element),
            operand1=ValueReference.from_xml(element[0]),
            operand2=tag_registry.from_child_xml(
                element[1],
                allowed_types=SpatialDescription.__args__,  # get_args() in 3.8
            ),
        )


@dataclass
@tag_registry.register_names(TemporalOperatorName)  # <After>, <Before>, ...
class TemporalOperator(NonIdOperator):
    """Comparisons with dates"""

    operatorType: TemporalOperatorName
    operand1: ValueReference
    operand2: TemporalOperand

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            operatorType=TemporalOperatorName.from_xml(element),
            operand1=ValueReference.from_xml(element[0]),
            operand2=tag_registry.from_child_xml(
                element[1], allowed_types=TemporalOperand.__args__,  # get_args() in 3.8
            ),
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
        )


@dataclass
@tag_registry.register("PropertyIsBetween")
class BetweenComparisonOperator(ComparisonOperator):
    """Check whether a value is between two elements."""

    expression: Expression
    lowerBoundary: Expression
    upperBoundary: Expression

    @classmethod
    def from_xml(cls, element: Element):
        lower = get_child(element, FES20, "LowerBoundary")
        upper = get_child(element, FES20, "UpperBoundary")
        return cls(
            expression=Expression.from_child_xml(element[0]),
            lowerBoundary=Expression.from_child_xml(lower[0]),
            upperBoundary=Expression.from_child_xml(upper[0]),
        )


@dataclass
@tag_registry.register("PropertyIsLike")
class LikeOperator(ComparisonOperator):
    """Perform wildcard matching."""

    expression: Tuple[Expression, Expression]
    wildCard: str
    singleChar: str
    escapeChar: str

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            expression=(
                Expression.from_child_xml(element[0]),
                Expression.from_child_xml(element[1]),
            ),
            wildCard=element.attrib["wildCard"],
            singleChar=element.attrib["singleChar"],
            escapeChar=element.attrib["escapeChar"],
        )


@dataclass
@tag_registry.register("PropertyIsNil")
class NilOperator(ComparisonOperator):
    """Check whether the value evaluates to null/None"""

    expression: Optional[Expression]
    nilReason: str

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            expression=Expression.from_child_xml(element[0]) if element else None,
            nilReason=element.get("nilReason"),
        )


@dataclass
@tag_registry.register("PropertyIsNull")
class NullOperator(ComparisonOperator):
    """Check whether the property exists."""

    expression: Expression

    @classmethod
    def from_xml(cls, element: Element):
        return cls(expression=Expression.from_child_xml(element[0]),)


class LogicalOperator(NonIdOperator):
    """Base class for AND, OR, NOT comparisons"""


@dataclass
@tag_registry.register("And")
@tag_registry.register("Or")
class BinaryLogicOperator(LogicalOperator):
    """Apply an AND or OR operator"""

    operands: List[NonIdOperator]
    operatorType: BinaryLogicType

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            operands=[NonIdOperator.from_child_xml(child) for child in element],
            operatorType=BinaryLogicType.from_xml(element),
        )


@dataclass
@tag_registry.register("Not")
class UnaryLogicOperator(LogicalOperator):
    """Apply a NOT operator"""

    operands: NonIdOperator
    operatorType: UnaryLogicType

    @classmethod
    def from_xml(cls, element: Element):
        return cls(
            operands=NonIdOperator.from_child_xml(element[0]),
            operatorType=UnaryLogicType.from_xml(element),
        )


class ExtensionOperator(NonIdOperator):
    """Base class for extensions to FES20"""
