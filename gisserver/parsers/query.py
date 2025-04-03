"""The intermediate query result used by the various ``build_...()`` methods."""

from __future__ import annotations

import operator
from datetime import date, datetime
from functools import reduce
from typing import Union

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import FieldError
from django.db.models import Q, QuerySet
from django.db.models.expressions import Combinable, Func

from gisserver.features import FeatureType

RhsTypes = Union[Combinable, Func, Q, GEOSGeometry, bool, int, str, date, datetime, tuple]


class CompiledQuery:
    """Intermediate data for translating FES queries to Django.

    This class effectively contains all data from the ``<fes:Filter>`` object,
    but using a format that can be translated to a django QuerySet.

    As the Abstract Syntax Tree of a FES-filter creates the ORM query,
    it fills this object with all intermediate bits. This allows building
    the final QuerySet object in a single round. Each ``build_...()`` method
    in the tree may add extra lookups and annotations.
    """

    def __init__(
        self,
        feature_type: FeatureType | None = None,
        using: str | None = None,
        lookups: list[Q] | None = None,
        typed_lookups: dict[str, list[Q]] | None = None,
        annotations: dict[str, Combinable | Q] | None = None,
    ):
        """
        :param feature_type: The feature type this query uses.
        :param using: The Django database alias.

        The extra parameters of the init method ar typically used only in unit tests.
        """
        self.feature_type = feature_type
        self.using = using
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

    def filter_queryset(self, queryset: QuerySet, feature_type: FeatureType) -> QuerySet:
        """Apply the filters and lookups to the queryset.

        :param queryset: The queryset to filter.
        :param feature_type: The feature type that the queryset originated from.
        """
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
            lookups += self.typed_lookups[feature_type.name]
        except KeyError:
            pass

        if lookups:
            try:
                queryset = queryset.filter(*lookups)
            except FieldError as e:
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
