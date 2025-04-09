"""These classes map to the FES 2.0 specification for operators.
The class names and attributes are identical to those in the FES spec.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from functools import cached_property, reduce
from itertools import groupby
from typing import Protocol, Union

from django.contrib.gis import measure
from django.db.models import Q

from gisserver.exceptions import ExternalParsingError, OperationProcessingFailed
from gisserver.parsers import gml
from gisserver.parsers.ast import (
    BaseNode,
    TagNameEnum,
    expect_children,
    expect_tag,
    tag_registry,
)
from gisserver.parsers.query import CompiledQuery, RhsTypes
from gisserver.parsers.xml import NSElement, xmlns

from .expressions import Expression, Literal, ValueReference
from .identifiers import Id
from .lookups import ARRAY_LOOKUPS  # also registers the lookups.

SpatialDescription = Union[gml.GM_Object, gml.GM_Envelope, ValueReference]
TemporalOperand = Union[gml.TM_Object, ValueReference]

# Fully qualified tag names
FES_VALUE_REFERENCE = xmlns.fes20.qname("ValueReference")
FES_DISTANCE = xmlns.fes20.qname("Distance")
FES_LOWER_BOUNDARY = xmlns.fes20.qname("LowerBoundary")
FES_UPPER_BOUNDARY = xmlns.fes20.qname("UpperBoundary")


class HasBuildRhs(Protocol):
    """Define interface for any class that has ``build_rhs()``."""

    def build_rhs(self, compiler) -> RhsTypes: ...


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
    This also maps their names to ORM field lookups.
    """

    PropertyIsEqualTo = "exact"
    PropertyIsNotEqualTo = "fes_notequal"  # custom FesNotEqualTo lookup
    PropertyIsLessThan = "lt"
    PropertyIsGreaterThan = "gt"
    PropertyIsLessThanOrEqualTo = "lte"
    PropertyIsGreaterThanOrEqualTo = "gte"


class DistanceOperatorName(TagNameEnum):
    """XML tag names mapped to distance operators for the ORM."""

    Beyond = "fes_beyond"  # using __distance_gt=.. would be slower.
    DWithin = "dwithin"  # ST_DWithin uses indices, distance_lte does not.


class SpatialOperatorName(TagNameEnum):
    """XML tag names mapped to geometry operators.

    The values correspond with GeoDjango operators. So a ``BBOX`` query
    will translate into ``geometry__intersects=Polygon(...)``.
    """

    # (A Within B) implies that (B Contains A)

    # BBOX can either be implemented using bboverlaps (more efficient), or the
    # more correct "intersects" option (e.g. a line near the box would match otherwise).
    BBOX = "intersects"  # ISO version: "NOT DISJOINT"
    Equals = "equals"  # Test whether two geometries are topologically equal
    Disjoint = "disjoint"  # Tests whether two geometries are disjoint (do not interact)
    Intersects = "intersects"  # Tests whether two geometries intersect
    Touches = "touches"  # Tests whether two geometries touch (e.g. country border).
    Crosses = "crosses"  # Tests whether two geometries cross (e.g. two streets).
    Within = "within"  # Tests a geometry is within another one (e.g. city within province).
    Contains = "contains"  # Tests a geometry contains another one (e.g. province contains city).
    Overlaps = "overlaps"  # Test whether two geometries overlap


class TemporalOperatorName(TagNameEnum):
    """XML tag names mapped to datetime operators.

    Explanation here: http://old.geotools.org/Temporal-Filters_211091519.html
    and: https://github.com/geotools/geotools/wiki/temporal-filters
    """

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
    """A measurement for a distance element.

    This parses and handles the syntax::

        <fes:Distance uom="...">value</fes:Distance>

    This element is used within the :class:`DistanceOperator` that
    handles the ``<fes:DWithin>`` and ``<fes:Beyond>`` tags.

    The "unit of measurement" (uom) supports most standard units, like meters (``m``),
    kilometers (``km``), nautical mile (``nm``), miles (``mi``), inches (``inch``).
    The full list can be found at: https://docs.djangoproject.com/en/5.1/ref/contrib/gis/measure/#supported-units
    """

    xml_ns = xmlns.fes20

    value: Decimal
    uom: str  # Unit of measurement, fes20:UomSymbol | fes20:UomURI

    @classmethod
    @expect_tag(xmlns.fes20, "Distance")
    def from_xml(cls, element: NSElement):
        return cls(value=Decimal(element.text), uom=element.get_attribute("uom"))

    def build_rhs(self, compiler) -> measure.Distance:
        return measure.Distance(default_unit=self.uom, **{self.uom: self.value})


class Operator(BaseNode):
    """Abstract base class, as defined by FES spec.

    This base class is also used in parsing; for example the ``<fes:Filter>``
    tag only allows ``Operator`` and ``Expression`` subclasses as allowed arguments.
    Having all those classes as Python types, makes it very easy to validate
    whether a given child element is the expected node type.
    """

    xml_ns = xmlns.fes20

    def build_query(self, compiler: CompiledQuery) -> Q | None:
        raise NotImplementedError(f"Using {self.__class__.__name__} is not supported yet.")


@dataclass
class IdOperator(Operator):
    """List of ResourceId objects"""

    id: list[Id]

    @property
    def type_names(self) -> list[str]:
        """Provide a list of all type names accessed by this operator"""
        return [type_name for type_name in self.grouped_ids if type_name is not None]

    @cached_property
    def grouped_ids(self) -> dict[str, list[Id]]:
        # For itertools.groupby(), items have to be sorted first.
        ids = sorted(self.id, key=operator.attrgetter("rid"))
        return {
            type_name: list(items)
            for type_name, items in groupby(ids, key=lambda id: id.get_type_name())
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
            ids_subset = reduce(operator.or_, [id.build_query(compiler) for id in items])
            compiler.add_lookups(ids_subset, type_name=type_name)


class NonIdOperator(Operator):
    """Abstract base class, as defined by FES spec.

    This is used for nearly all operators,
    except those that have <fes:ResourceId> elements as children.

    Some operators, such as the ``<fes:And>``, ``<fes:Or>`` and ``<fes:Not>`` operators
    explicitly support only ``NonIdOperator`` elements as arguments.
    Hence, having this base class as Python type simplifies parsing.
    """

    _source = None
    allow_geometries = False

    def build_compare(
        self,
        compiler: CompiledQuery,
        lhs: Expression,
        lookup: str,
        rhs: Expression | RhsTypes,
    ) -> Q:
        """Use the value in comparison with some other expression.

        This calls build_lhs() and build_rhs() on the expressions.
        """
        # lhs and rhs are allowed to be reversed. However, the SQL compiler
        # works much simpler when Django can predict the actual data type.
        if isinstance(lhs, Literal) and isinstance(rhs, ValueReference):
            lhs, rhs = rhs, lhs

        if compiler.feature_type is not None:
            lookup = self.validate_comparison(compiler, lhs, lookup, rhs)

        # Build Django Q-object
        lhs = lhs.build_lhs(compiler)

        if isinstance(rhs, (Expression, gml.GM_Object)):
            rhs = rhs.build_rhs(compiler)

        comparison = Q(**{f"{lhs}__{lookup}": rhs})
        return compiler.apply_extra_lookups(comparison)

    def validate_comparison(
        self,
        compiler: CompiledQuery,
        lhs: Expression,
        lookup: str,
        rhs: Expression | RhsTypes,
    ):
        """Validate whether a given comparison is even possible.

        For example, comparisons like ``name == "test"`` are fine,
        but ``geometry < 4`` or ``datefield == 35.2" raise an error.

        The lhs/rhs are expected to be ordered in a logical sequence.
        So ``<value> == <element>`` should be provided as ``<element> == <value>``.

        :param compiler: The object that holds the intermediate state
        :param lhs: The left-hand-side of the comparison (e.g. the element).
        :param lookup: The ORM lookup expression being used (e.g. ``equals``).
        :param rhs: The right-hand-side of the comparison (e.g. the value).
        """
        if isinstance(lhs, ValueReference):
            xsd_element = compiler.feature_type.resolve_element(lhs.xpath).child
            tag = self._source if self._source is not None else None

            # e.g. deny <PropertyIsLessThanOrEqualTo> against <gml:boundedBy>
            if xsd_element.type.is_geometry and not self.allow_geometries:
                raise OperationProcessingFailed(
                    f"Operator '{tag}' does not support comparing"
                    f" geometry properties: '{xsd_element.xml_name}'.",
                    locator="filter",
                    status_code=400,  # not HTTP 500 here. Spec allows both.
                )

            if isinstance(rhs, Literal):
                # Since the element is resolved, inform the Literal how to parse the value.
                # This avoids various validation errors along the path.
                rhs.bind_type(xsd_element.type)

                # When a common case of value comparison is done, the inputs
                # can be validated before the ORM query is constructed.
                xsd_element.validate_comparison(rhs.raw_value, lookup=lookup, tag=tag)

            # Checking scalar values against array fields will fail.
            # However, to make the queries consistent with other unbounded types (i.e. M2M fields),
            # it makes sense to return an object when *one* entry in the array matches.
            if xsd_element.is_array:
                try:
                    return ARRAY_LOOKUPS[lookup]
                except KeyError:
                    raise OperationProcessingFailed(
                        f"Operator '{tag}' is not supported for "
                        f"the '{xsd_element.name}' property.",
                        locator="filter",
                        status_code=400,  # not HTTP 500 here. Spec allows both.
                    ) from None

        return lookup

    def build_compare_between(
        self,
        compiler: CompiledQuery,
        lhs: Expression,
        lookup: str,
        rhs: tuple[HasBuildRhs, HasBuildRhs],
    ) -> Q:
        """Use the value in comparison with 2 other values (e.g. between query)"""
        if compiler.feature_type is not None:
            self.validate_comparison(compiler, lhs, lookup, rhs[0])
            self.validate_comparison(compiler, lhs, lookup, rhs[1])

        field_name = lhs.build_lhs(compiler)
        comparison = Q(
            **{
                f"{field_name}__{lookup}": (
                    rhs[0].build_rhs(compiler),
                    rhs[1].build_rhs(compiler),
                )
            }
        )
        return compiler.apply_extra_lookups(comparison)


class SpatialOperator(NonIdOperator):
    """Abstract base class, as defined by FES spec."""


@dataclass
@tag_registry.register("Beyond")
@tag_registry.register("DWithin")
class DistanceOperator(SpatialOperator):
    """Comparing the distance to a geometry.

    This parses and handles the syntax::

        <fes:DWithin>
            <fes:ValueReference>geometry</fes:ValueReference>
            <gml:Point srsDimension="2">
                <gml:pos>43.55749 1.525864</gml:pos>
            </gml:Point>
            <fes:Distance oum="m:>100</fes:Distance>
        </fes:DWithin>
    """

    allow_geometries = True  # override static attribute

    valueReference: ValueReference
    operatorType: DistanceOperatorName
    geometry: gml.GM_Object
    distance: Measure
    _source: str | None = field(compare=False, default=None)

    @classmethod
    @expect_children(3, ValueReference, gml.GM_Object, Measure)
    def from_xml(cls, element: NSElement):
        geometries = gml.find_gml_nodes(element)
        if not geometries:
            raise ExternalParsingError(f"Missing gml element in <{element.tag}>")
        elif len(geometries) > 1:
            raise ExternalParsingError(f"Multiple gml elements found in <{element.tag}>")

        return cls(
            valueReference=ValueReference.from_xml(element.find(FES_VALUE_REFERENCE)),
            operatorType=DistanceOperatorName.from_xml(element),
            geometry=gml.parse_gml_node(geometries[0]),
            distance=Measure.from_xml(element.find(FES_DISTANCE)),
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
@tag_registry.register(SpatialOperatorName)  # <BBOX>, <Equals>, ...
class BinarySpatialOperator(SpatialOperator):
    """A comparison of geometries using 2 values, e.g. A Within B.

    This parses and handles the syntax, and its variants::

        <fes:BBOX>
            <fes:ValueReference>Geometry</fes:ValueReference>
            <gml:Envelope srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                <gml:lowerCorner>13.0983 31.5899</gml:lowerCorner>
                <gml:upperCorner>35.5472 42.8143</gml:upperCorner>
            </gml:Envelope>
        </fes:BBOX>

    It also handles the ``<fes:Equals>``, ``<fes:Within>``, ``<fes:Intersects>``, etc..
    that exist in the :class:`SpatialOperatorName` enum.
    """

    allow_geometries = True  # override static attribute

    operatorType: SpatialOperatorName
    operand1: ValueReference | None
    operand2: SpatialDescription
    _source: str | None = field(compare=False, default=None)

    @classmethod
    def from_xml(cls, element: NSElement):
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
            operand2=tag_registry.node_from_xml(geo, allowed_types=SpatialDescription.__args__),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        operant1 = self.operand1
        if operant1 is None:
            operant1 = ValueReference(xpath=compiler.feature_type.main_geometry_element.orm_path)

        return self.build_compare(
            compiler,
            lhs=operant1,
            lookup=self.operatorType.value,
            rhs=self.operand2,
        )


@dataclass
@tag_registry.register(TemporalOperatorName)  # <After>, <Before>, ...
class TemporalOperator(NonIdOperator):
    """Comparisons with dates.

    For these operators, only the parsing is implemented.
    These are not translated into ORM queries yet.

    It supports a syntax such as::

       <fes:TEquals>
          <fes:ValueReference>SimpleTrajectory/gml:validTime/gml:TimeInstant</fes:ValueReference>
          <gml:TimeInstant gml:id="TI1">
             <gml:timePosition>2005-05-19T09:28:40Z</gml:timePosition>
          </gml:TimeInstant>
       </fes:TEquals>

    or::

       <fes:During>
          <fes:ValueReference>SimpleTrajectory/gml:validTime/gml:TimeInstant</fes:ValueReference>
          <gml:TimePeriod gml:id="TP1">
             <gml:begin>
                <gml:TimeInstant gml:id="TI1">
                   <gml:timePosition>2005-05-17T00:00:00Z</gml:timePosition>
                </gml:TimeInstant>
             </gml:begin>
             <gml:end>
                <gml:TimeInstant gml:id="TI2">
                   <gml:timePosition>2005-05-23T00:00:00Z</gml:timePosition>
                </gml:TimeInstant>
             </gml:end>
          </gml:TimePeriod>
       </fes:During>
    """

    operatorType: TemporalOperatorName
    operand1: ValueReference
    operand2: TemporalOperand
    _source: str | None = field(compare=False, default=None)

    @classmethod
    @expect_children(2, ValueReference, *TemporalOperand.__args__)
    def from_xml(cls, element: NSElement):
        return cls(
            operatorType=TemporalOperatorName.from_xml(element),
            operand1=ValueReference.from_xml(element[0]),
            operand2=tag_registry.node_from_xml(
                element[1], allowed_types=TemporalOperand.__args__
            ),
            _source=element.tag,
        )


class ComparisonOperator(NonIdOperator):
    """Base class for comparisons.
    This class name mirrors the fes-spec name,
    and allows grouping various comparisons together.
    """

    # Start counting fresh here, to collect the capabilities
    # that are listed in the <fes20:ComparisonOperators> node:
    xml_tags = []


@dataclass
@tag_registry.register(BinaryComparisonName)  # <PropertyIs...>
class BinaryComparisonOperator(ComparisonOperator):
    """A comparison between 2 values, e.g. A == B.

    This parses and handles the syntax::

        <fes:PropertyIsEqualTo>
            <fes:ValueReference>city/name</fes:ValueReference>
            <fes:Literal>CloudCity</fes:Literal>
        </fes:PropertyIsEqualTo>

    ...and all variations (``<fes:PropertyIsLessThan>``, etc...)
    that are listed in the :class:`BinaryComparisonName` enum.

    Note that both arguments are expressions, so these can be value references, literals
    or functions. The ``<fes:Literal>`` element may hold a GML element as its value.
    """

    operatorType: BinaryComparisonName
    expression: tuple[Expression, Expression]
    matchCase: bool = True
    matchAction: MatchAction = MatchAction.Any
    _source: str | None = field(compare=False, default=None)

    @classmethod
    @expect_children(2, Expression, Expression)
    def from_xml(cls, element: NSElement):
        return cls(
            operatorType=BinaryComparisonName.from_xml(element),
            expression=(
                Expression.child_from_xml(element[0]),
                Expression.child_from_xml(element[1]),
            ),
            matchCase=element.get("matchCase", True),
            matchAction=MatchAction(element.get("matchAction", default=MatchAction.Any)),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        lhs, rhs = self.expression
        return self.build_compare(compiler, lhs=lhs, lookup=self.operatorType.value, rhs=rhs)


@dataclass
@tag_registry.register("PropertyIsBetween")
class BetweenComparisonOperator(ComparisonOperator):
    """Check whether a value is between two elements.

    This parses and handles the syntax::

        <fes:PropertyIsBetween>
            <fes:ValueReference>DEPTH</fes:ValueReference>
            <fes:LowerBoundary><fes:Literal>100</fes:Literal></fes:LowerBoundary>
            <fes:UpperBoundary><fes:Literal>200</fes:Literal></fes:UpperBoundary>
        </fes:PropertyIsBetween>

    Note that both boundary arguments receive expressions, so these can be value
    references, literals or functions!
    """

    expression: Expression
    lowerBoundary: Expression
    upperBoundary: Expression
    _source: str | None = field(compare=False, default=None)

    @classmethod
    @expect_children(3, Expression, "LowerBoundary", "UpperBoundary")
    def from_xml(cls, element: NSElement):
        if (element[1].tag != FES_LOWER_BOUNDARY) or (element[2].tag != FES_UPPER_BOUNDARY):
            raise ExternalParsingError(
                f"{element.tag} should have 3 child nodes: "
                f"(expression), <LowerBoundary>, <UpperBoundary>"
            )

        lower = element[1]
        upper = element[2]

        if len(lower) != 1:
            raise ExternalParsingError(f"{lower.tag} should have 1 expression child node")
        if len(upper) != 1:
            raise ExternalParsingError(f"{upper.tag} should have 1 expression child node")

        return cls(
            expression=Expression.child_from_xml(element[0]),
            lowerBoundary=Expression.child_from_xml(lower[0]),
            upperBoundary=Expression.child_from_xml(upper[0]),
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
    """Perform wildcard matching.

    This parses and handles the syntax::

        <fes:PropertyIsLike wildCard="*" singleChar="#" escapeChar="!">
            <fes:ValueReference>last_name</fes:ValueReference>
            <fes:Literal>John*</fes:Literal>
        </fes:PropertyIsLike>
    """

    expression: tuple[Expression, Expression]
    wildCard: str
    singleChar: str
    escapeChar: str
    _source: str | None = field(compare=False, default=None)

    @classmethod
    @expect_children(2, Expression, Expression)
    def from_xml(cls, element: NSElement):
        return cls(
            expression=(
                Expression.child_from_xml(element[0]),
                Expression.child_from_xml(element[1]),
            ),
            # These attributes are required by the WFS spec:
            wildCard=element.get_attribute("wildCard"),
            singleChar=element.get_attribute("singleChar"),
            escapeChar=element.get_attribute("escapeChar"),
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
            raise ExternalParsingError(f"Expected a literal value for the {self.tag} operator.")

        # Use the FesLike lookup
        return self.build_compare(compiler, lhs=lhs, lookup="fes_like", rhs=rhs)


@dataclass
@tag_registry.register("PropertyIsNil")
class NilOperator(ComparisonOperator):
    """Check whether the value evaluates to null/None.
    If the WFS returned a property element with <tns:p xsi:nil='true'>, this returns true.

    It parses and handles syntax such as::

        <fes:PropertyIsNil>
            <fes:ValueReference>city/name</fes:ValueReference>
        </fes:PropertyIsNil>

    Note that the provided argument can be any expression, not just a value reference.
    Thus, it can also check whether a function returns null.
    """

    expression: Expression | None
    nilReason: str
    _source: str | None = field(compare=False, default=None)

    @classmethod
    @expect_children(1, Expression)
    def from_xml(cls, element: NSElement):
        return cls(
            expression=Expression.child_from_xml(element[0]) if element is not None else None,
            nilReason=element.get("nilReason"),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        # Any value that evaluates to None is returned as 'xs:nil' in our output.
        return self.build_compare(compiler, lhs=self.expression, lookup="isnull", rhs=True)


@dataclass
@tag_registry.register("PropertyIsNull")
class NullOperator(ComparisonOperator):
    """Check whether the property exists.
    If the WFS would not return the property element <tns:p>, this returns true.

    It parses and handles syntax such as::

        <fes:PropertyIsNull>
            <fes:ValueReference>city/name</fes:ValueReference>
        </fes:PropertyIsNull>

    Note that the provided argument can be any expression, not just a value reference.
    """

    expression: Expression
    _source: str | None = field(compare=False, default=None)

    @classmethod
    @expect_children(1, Expression)
    def from_xml(cls, element: NSElement):
        return cls(expression=Expression.child_from_xml(element[0]), _source=element.tag)

    def build_query(self, compiler: CompiledQuery) -> Q:
        # For now, the implementation is identical to PropertyIsNil.
        # According to the WFS spec, this should only be true when the element
        # is not returned at all (minOccurs=0).
        # TODO: this happens for maxOccurs=unbounded with a null value.
        return self.build_compare(compiler, lhs=self.expression, lookup="isnull", rhs=True)


class LogicalOperator(NonIdOperator):
    """Base class in the fes-spec for AND, OR, NOT comparisons"""


@dataclass
@tag_registry.register("And")
@tag_registry.register("Or")
class BinaryLogicOperator(LogicalOperator):
    """Apply an 'AND' or 'OR' operator.

    This parses and handles the syntax::

        <fes:And>
            <fes:PropertyIsGreaterThanOrEqualTo>
                ...
            </fes:PropertyIsGreaterThanOrEqualTo>
            <fes:BBOX>
                ...
            </fes:BBOX>
        </fes:And>

    Any tag deriving from :class:`NonIdOperator` is allowed here.
    """

    operands: list[NonIdOperator]
    operatorType: BinaryLogicType
    _source: str | None = field(compare=False, default=None)

    @classmethod
    @expect_children(2, NonIdOperator, NonIdOperator)
    def from_xml(cls, element: NSElement):
        return cls(
            operands=[NonIdOperator.child_from_xml(child) for child in element],
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
    """Apply a NOT operator.

    This parses and handles the syntax::

        <fes:Not>
            <fes:PropertyIsNil>
                <fes:ValueReference>city/name</fes:ValueReference>
            </fes:PropertyIsNil>
        </fes:Not>
    """

    operands: NonIdOperator
    operatorType: UnaryLogicType
    _source: str | None = field(compare=False, default=None)

    @classmethod
    @expect_children(1, NonIdOperator)
    def from_xml(cls, element: NSElement):
        return cls(
            operands=NonIdOperator.child_from_xml(element[0]),
            operatorType=UnaryLogicType.from_xml(element),
            _source=element.tag,
        )

    def build_query(self, compiler: CompiledQuery) -> Q:
        """Apply the NOT operation to the Q-object"""
        return self.operatorType.value(self.operands.build_query(compiler))


class ExtensionOperator(NonIdOperator):
    """Base class for extensions to FES 2.0.

    It's fully allowed to introduce new operators on your own namespace.
    These need to inherit from this class.
    """
