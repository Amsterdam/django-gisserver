from __future__ import annotations

from dataclasses import dataclass, field
from typing import AnyStr, ClassVar, Union

from django.db.models import Q

from gisserver.exceptions import InvalidParameterValue
from gisserver.parsers.ast import AstNode, expect_tag, tag_registry
from gisserver.parsers.gml import GEOSGMLGeometry
from gisserver.parsers.ows import KVPRequest
from gisserver.parsers.query import CompiledQuery
from gisserver.parsers.xml import NSElement, parse_xml_from_string, xmlns

from . import expressions, identifiers, operators

#: The FES element group that can be used as body for the :class:`Filter` element.
FilterPredicates = Union[expressions.Function, operators.Operator]

# Fully qualified tag names
FES_RESOURCE_ID = xmlns.fes20.qname("ResourceId")


@dataclass
@tag_registry.register("Filter", xmlns.fes20)
class Filter(AstNode):
    """The ``<fes:Filter>`` element.

    This parses and handles the syntax::

        <fes:Filter>
            <fes:SomeOperator>
                ...
            </fes:SomeOperator>
        </fes:Filter>

    The :meth:`build_query` will convert the parsed tree
    into a format that can build a Django ORM QuerySet.

    .. seealso:: https://www.mediamaps.ch/ogc/schemas-xsdoc/sld/1.2/filter_xsd.html#Filter
    """

    query_language: ClassVar[str] = "urn:ogc:def:queryLanguage:OGC-FES:Filter"

    #: The filter predicate (body)
    predicate: FilterPredicates

    source: AnyStr | None = field(default=None, compare=False)

    @classmethod
    def from_kvp_request(cls, kvp: KVPRequest) -> Filter | None:
        """Parse the filter from the GET request."""

        # Check filter language
        filter_language = kvp.get_str("FILTER_LANGUAGE", default=cls.query_language)
        if filter_language != cls.query_language:
            raise InvalidParameterValue(
                f"Invalid value for filterLanguage: {filter_language}", locator="filterLanguage"
            )

        # Parse filter
        filter = kvp.get_custom(
            "filter", default=None, parser=lambda x: cls.from_string(x, kvp.ns_aliases)
        )

        # Parse alternatives to filter
        resource_ids = [
            identifiers.ResourceId.from_string(rid, kvp.ns_aliases)
            for rid in kvp.get_list("resourceID", default=[])
        ]
        bbox = kvp.get_custom("bbox", default=None, parser=GEOSGMLGeometry.from_bbox)

        # Make sure the various query options are not mixed.
        cls.validate_kvp_exclusions(filter, bbox, resource_ids)

        if filter is None:
            # See if the other KVP parameters still provide a basic filter.
            # Instead of implementing these parameters separately in the AdhocQueryExpression,
            # they are implemented by constructing the filter AST internally.
            if resource_ids:
                filter = Filter(predicate=operators.IdOperator(resource_ids))
            elif bbox is not None:
                filter = Filter(
                    predicate=operators.BinarySpatialOperator(
                        operatorType=operators.SpatialOperatorName.BBOX,
                        operand1=None,
                        operand2=bbox,
                    )
                )

        return filter

    @classmethod
    def validate_kvp_exclusions(
        cls, filter: Filter | None, bbox: GEOSGMLGeometry | None, resource_ids: list
    ):
        """Validate mutually exclusive parameters"""
        if filter is not None and (bbox is not None or resource_ids):
            raise InvalidParameterValue(
                "The FILTER parameter is mutually exclusive with BBOX and RESOURCEID",
                locator="filter",
            )

        if resource_ids and (bbox is not None or filter is not None):
            raise InvalidParameterValue(
                "The RESOURCEID parameter is mutually exclusive with BBOX and FILTER",
                locator="resourceId",
            )

    @classmethod
    def from_string(cls, text: AnyStr, ns_aliases: dict[str, str] | None = None) -> Filter:
        """Parse an XML ``<fes:Filter>`` string.

        This uses defusedxml by default, to avoid various XML injection attacks.

        :raises ValueError: When data is incorrect, or XML has syntax errors.
        :raises NotImplementedError: When unsupported features are called.
        """
        if isinstance(text, str):
            end_first = text.index(">")
            first_tag = text[:end_first].lstrip()
            # Allow KVP requests without a namespace
            # Both geoserver and mapserver support this.
            if "xmlns" not in first_tag and (
                first_tag == "<Filter" or first_tag.startswith("<Filter ")
            ):
                text = f'{first_tag} xmlns="{xmlns.fes20}" xmlns:gml="{xmlns.gml32}"{text[end_first:]}'

        root_element = parse_xml_from_string(text, extra_ns_aliases=ns_aliases)
        return Filter.from_xml(root_element, source=text)

    @classmethod
    @expect_tag(xmlns.fes20, "Filter")
    def from_xml(cls, element: NSElement, source: AnyStr | None = None) -> Filter:
        """Parse the <fes20:Filter> element."""
        if len(element) > 1 or element[0].tag == FES_RESOURCE_ID:
            # fes20:ResourceId is the only element that may appear multiple times.
            # Wrap it in an IdOperator so this class can have a single element as predicate.
            return Filter(
                predicate=operators.IdOperator(
                    [identifiers.Id.child_from_xml(child) for child in element]
                ),
                source=source,
            )
        else:
            return Filter(
                # Can be Function or Operator (e.g. BinaryComparisonOperator),
                # but not Literal or ValueReference.
                predicate=tag_registry.node_from_xml(
                    element[0], allowed_types=FilterPredicates.__args__
                ),
                source=source,
            )

    def build_query(self, compiler: CompiledQuery) -> Q | None:
        """Collect the data to perform a Django ORM query."""
        # Function, Operator, IdList
        # The operators may add the logic themselves, or return a Q object.
        return self.predicate.build_query(compiler)

    def get_resource_id_types(self) -> list[str] | None:
        """When the filter predicate consists of ``<fes:ResourceId>`` elements, return those.
        This can return an empty list in case a ``<fes:ResourceId>`` object doesn't define a type.
        """
        if isinstance(self.predicate, operators.IdOperator):
            return self.predicate.get_type_names()
        else:
            return None
