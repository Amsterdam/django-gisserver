"""The intermediate query result used by the various ``build_...()`` methods."""

from __future__ import annotations

import logging
import operator
from datetime import date, datetime
from decimal import Decimal as D
from functools import reduce

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import FieldError
from django.db.models import Q, QuerySet
from django.db.models.expressions import Combinable, Func

from gisserver.features import FeatureType

logger = logging.getLogger(__name__)
ScalarTypes = bool | int | str | D | date | datetime
RhsTypes = Combinable | Func | Q | GEOSGeometry | bool | int | D | str | date | datetime | tuple


class CompiledQuery:
    """Intermediate data for translating FES queries to Django.

    This class effectively contains all data from the ``<fes:Filter>`` object,
    but using a format that can be translated to a Django QuerySet.

    As the Abstract Syntax Tree of a FES-filter creates the ORM query,
    it fills this object with all intermediate bits. This allows building
    the final QuerySet object in a single round. Each ``build_...()`` method
    in the tree may add extra lookups and annotations.
    """

    def __init__(
        self,
        feature_types: list[FeatureType],
        lookups: list[Q] | None = None,
        typed_lookups: dict[str, list[Q]] | None = None,
        annotations: dict[str, Combinable | Q] | None = None,
    ):
        """
        :param feature_types: The feature types this query uses.
                              Typically, this is one feature unless a JOIN syntax is used.

        The extra parameters of the init method ar typically used only in unit tests.
        """
        self.feature_types = feature_types
        self.lookups = lookups or []
        self.typed_lookups = typed_lookups or {}
        self.annotations = annotations or {}
        self.aliases = 0
        self.extra_lookups: list[Q] = []
        self.ordering: list[str] = []
        self.is_empty = False
        self.distinct = False

    def add_annotation(self, value: Combinable | Q) -> str:
        """Create a named-alias for a function/Q object.
        This alias can be used in a comparison, where expressions are used as left-hand-side.
        """
        self.aliases += 1
        name = f"a{self.aliases}"
        self.annotations[name] = value
        return name

    def add_distinct(self):
        """Enforce "SELECT DISTINCT" on the query, used when joining 1-N or N-M relationships."""
        self.distinct = True

    def add_lookups(self, q_object: Q, type_name: str | None = None):
        """Register an extra 'WHERE' clause of the query.
        This is used for comparisons, ID selectors and other query types.
        """
        if not isinstance(q_object, Q):
            raise TypeError()

        if type_name is not None:
            if type_name not in self.typed_lookups:
                self.typed_lookups[type_name] = []
            self.typed_lookups[type_name].append(q_object)
        else:
            self.lookups.append(q_object)

    def add_extra_lookup(self, q_object: Q):
        """Temporary stash an extra lookup that the expression can't return yet.
        This is used for XPath selectors that also filter on attributes,
        e.g. "element[@attr=..]/child". The attribute lookup is processed as another filter.
        """
        if not isinstance(q_object, Q):
            raise TypeError()
        # Note the ORM also provides a FilteredRelation() option, that is not explored yet here.
        self.extra_lookups.append(q_object)

    def add_ordering(self, ordering: list[str]):
        """Read the desired result ordering from a ``<fes:SortBy>`` element."""
        self.ordering.extend(ordering)

    def apply_extra_lookups(self, comparison: Q) -> Q:
        """Combine stashed lookups with the provided Q object.

        This is called for functions that compile a "Q" object.
        In case a node added extra lookups (for attributes), these are combined here
        with the actual comparison.
        """
        if not self.extra_lookups:
            return comparison

        # The extra lookups are used for XPath queries such as "/node[@attr=..]/foo".
        # A <ValueReference> with such lookup also requires to limit the filtered results,
        # in addition to the comparison operator code that is wrapped up here.
        result = reduce(operator.and_, [comparison] + self.extra_lookups)
        self.extra_lookups.clear()
        return result

    def mark_empty(self):
        """Mark as returning no results."""
        self.is_empty = True

    def get_queryset(self) -> QuerySet:
        """Apply the filters and lookups to the queryset."""
        queryset = self.feature_types[0].get_queryset()
        if self.is_empty:
            return queryset.none()

        if self.extra_lookups:
            # Each time an expression node calls add_extra_lookup(),
            # the parent should have used apply_extra_lookups()
            raise RuntimeError("apply_extra_lookups() was not called")

        # All are applied at once.
        if self.annotations:
            queryset = queryset.annotate(**self.annotations)

        lookups = self.lookups
        try:
            lookups += self.typed_lookups.pop(self.feature_types[0].xml_name)
        except KeyError:
            pass
        if self.typed_lookups:
            raise RuntimeError(
                "Types lookups defined for unknown feature types: %r", list(self.typed_lookups)
            )

        if lookups:
            try:
                queryset = queryset.filter(*lookups)
            except FieldError as e:
                logger.debug("Query failed: %s, constructed query: %r", e.args[0], lookups)
                e.args = (f"{e.args[0]} Constructed query: {lookups!r}",) + e.args[1:]
                raise

        if self.ordering:
            queryset = queryset.order_by(*self.ordering)

        if self.distinct:
            queryset = queryset.distinct()

        return queryset

    def __repr__(self):
        return (
            "<CompiledQuery"
            f" annotations={self.annotations!r},"
            f" lookups={self.lookups!r},"
            f" typed_lookups={self.typed_lookups!r}>"
        )

    def __eq__(self, other):
        """For pytest comparisons."""
        if isinstance(other, CompiledQuery):
            return (
                other.lookups == self.lookups
                and other.typed_lookups == self.typed_lookups
                and other.annotations == self.annotations
            )
        else:
            return NotImplemented
