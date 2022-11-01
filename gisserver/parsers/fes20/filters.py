from __future__ import annotations

from typing import AnyStr, Union
from xml.etree.ElementTree import Element, QName

from defusedxml.ElementTree import ParseError, fromstring

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.base import tag_registry
from gisserver.parsers.tags import expect_tag
from gisserver.types import FES20, GML32

from . import expressions, identifiers, operators, query

FilterPredicates = Union[expressions.Function, operators.Operator]


class Filter:
    """The <fes:Filter> element.

    As this is a wrapper, it only contains a "predicate" element with the contents.
    """

    query_language = "urn:ogc:def:queryLanguage:OGC-FES:Filter"

    predicate: FilterPredicates
    source: AnyStr | None

    def __init__(self, predicate: FilterPredicates, source: AnyStr | None = None):
        self.predicate = predicate
        self.source = source

    @classmethod
    def from_string(cls, text: AnyStr) -> Filter:
        """Parse an XML <fes20:Filter> string.

        This uses defusedxml by default, to avoid various XML injection attacks.

        :raises ValueError: When data is incorrect, or XML has syntax errors.
        :raises NotImplementedError: When unsupported features are called.
        """
        if isinstance(text, str):
            end_first = text.index(">")
            first_tag = text[:end_first].lstrip()
            if "xmlns" not in first_tag:
                # Allow KVP requests without a namespace
                # Both geoserver and mapserver support this.
                if first_tag == "<Filter" or first_tag.startswith("<Filter "):
                    text = f'{first_tag} xmlns="{FES20}" xmlns:gml="{GML32}"{text[end_first:]}'

        try:
            root_element = fromstring(text)
        except ParseError as e:
            # Offer consistent results for callers to check for invalid data.
            raise ExternalParsingError(str(e)) from e
        return Filter.from_xml(root_element, source=text)

    @classmethod
    @expect_tag(FES20, "Filter")
    def from_xml(cls, element: Element, source: AnyStr | None = None) -> Filter:
        """Parse the <fes20:Filter> element."""
        if len(element) > 1 or element[0].tag == QName(FES20, "ResourceId"):
            # fes20:ResourceId is the only element that may appear multiple times.
            return Filter(
                predicate=operators.IdOperator(
                    [identifiers.Id.from_child_xml(child) for child in element]
                ),
                source=source,
            )
        else:
            return Filter(
                predicate=tag_registry.from_child_xml(
                    element[0], allowed_types=(expressions.Function, operators.Operator)
                ),
                source=source,
            )

    def compile_query(self, feature_type=None, using=None) -> query.CompiledQuery:
        """Collect the data to perform a Django ORM query."""
        compiler = query.CompiledQuery(feature_type=feature_type, using=using)

        # Function, Operator, IdList
        q_object = self.predicate.build_query(compiler)
        if q_object is not None:
            compiler.add_lookups(q_object)

        return compiler

    def __repr__(self):
        return f"Filter(predicate={self.predicate!r}, source={self.source})"

    def __eq__(self, other):
        if isinstance(other, Filter):
            return self.predicate == other.predicate
        else:
            return NotImplemented
