from dataclasses import dataclass
from typing import AnyStr, Union
from xml.etree.ElementTree import Element, QName

from defusedxml.ElementTree import fromstring, ParseError
from django.db.models import QuerySet

from gisserver.parsers.base import FES20, tag_registry
from gisserver.parsers.utils import expect_tag
from . import expressions, identifiers, operators, query

FilterPredicates = Union[expressions.Function, identifiers.IdList, operators.Operator]


@dataclass
class Filter:
    """The <fes:Filter> element.

    As this is a wrapper, it only contains a "predicate" element with the contents.
    """

    query_language = "urn:ogc:def:queryLanguage:OGC-FES:Filter"

    predicate: FilterPredicates

    @classmethod
    def from_string(cls, text: AnyStr) -> "Filter":
        """Parse an XML <fes20:Filter> string.

        This uses defusedxml by default, to avoid various XML injection attacks.

        :raises ValueError: When data is incorrect, or XML has syntax errors.
        :raises NotImplementedError: When unsupported features are called.
        """
        try:
            root_element = fromstring(text)
        except ParseError as e:
            # Offer consistent results for callers to check for invalid data.
            raise ValueError(f"Syntax error in filter: {e}") from e
        return Filter.from_xml(root_element)

    @classmethod
    @expect_tag(FES20, "Filter")
    def from_xml(cls, element: Element) -> "Filter":
        """Parse the <fes20:Filter> element."""
        if len(element) > 1 or element[0].tag == QName(FES20, "ResourceId"):
            # fes20:ResourceId is the only element that may appear multiple times.
            return Filter(
                predicate=identifiers.IdList(
                    [identifiers.Id.from_child_xml(child) for child in element]
                )
            )
        else:
            return Filter(
                predicate=tag_registry.from_child_xml(
                    element[0], allowed_types=(expressions.Function, operators.Operator)
                )
            )

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        """Apply this filter to a Django QuerySet."""
        fesquery = self.get_query()
        return fesquery.filter_queryset(queryset)

    def get_query(self) -> query.FesQuery:
        """Collect the data to perform a Django ORM query."""
        fesquery = query.FesQuery()

        # Function, Operator, IdList
        q_object = self.predicate.build_query(fesquery)
        if q_object is not None:
            fesquery.add_lookups(q_object)

        return fesquery
