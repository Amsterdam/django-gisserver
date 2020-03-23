import operator
from functools import reduce
from typing import Union

from django.contrib.gis.db.models.fields import BaseSpatialField
from django.contrib.gis.db.models.lookups import DistanceLookupBase
from django.db import models
from django.db.models import Q, QuerySet, lookups
from django.db.models.expressions import Combinable

from . import expressions


class FesQuery:
    """Collect all data to query a Django queryset.

    This object is passed though all build_...() methods,
    so it can be used to add extra lookups and annotations.
    """

    def __init__(self, lookups=None, annotations=None):
        self.lookups = lookups or []
        self.annotations = annotations or {}
        self.aliases = 0
        self.extra_lookups = []
        self.sort_by = []

    def add_annotation(self, value: Union[Combinable, Q]) -> str:
        """Create an named-alias for a function/Q object.

        This alias can be used as left-hand-side of the query expression.
        """
        self.aliases += 1
        name = f"a{self.aliases}"
        self.annotations[name] = value
        return name

    def add_lookups(self, q_object: Q):
        """Register an extra 'WHERE' clause of the query."""
        if not isinstance(q_object, Q):
            raise TypeError()
        self.lookups.append(q_object)

    def add_extra_lookup(self, q_object: Q):
        """Temporary stash an extra lookup that the expression can't return yet."""
        if not isinstance(q_object, Q):
            raise TypeError()
        self.extra_lookups.append(q_object)

    def add_sort_by(self, sort_by: list):
        self.sort_by += sort_by

    def add_value_reference(self, value_reference: expressions.ValueReference) -> str:
        """Add a reference that should be returned by the query.

        This includes the XPath expression to the query, in case that adds
        extra lookups. The name (or alias) is returned that can be used in the
         ``queryset.values()`` result
        """
        return value_reference.build_rhs(self)

    def apply_extra_lookups(self, result: Q) -> Q:
        """Combine stashed lookups with the produced result."""
        if self.extra_lookups:
            result = reduce(operator.and_, [result] + self.extra_lookups)
            self.extra_lookups.clear()
        return result

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        """Apply the filters and lookups to the queryset"""
        if self.extra_lookups:
            # Each time an expression node calls add_extra_lookup(),
            # the parent should have used apply_extra_lookups()
            raise RuntimeError("apply_extra_lookups() was not called")

        # All are applied at once.
        if self.annotations:
            queryset = queryset.annotate(**self.annotations)

        if self.lookups:
            queryset = queryset.filter(*self.lookups)

        if self.sort_by:
            queryset = queryset.order_by(*self.sort_by)

        return queryset

    def __repr__(self):
        return f"<FesQuery annotations={self.annotations!r}, lookups={self.lookups!r}>"

    def __eq__(self, other):
        """For pytest comparisons."""
        if isinstance(other, FesQuery):
            return (
                other.lookups == self.lookups and other.annotations == self.annotations
            )
        else:
            return NotImplemented


@models.Field.register_lookup
class FesLike(lookups.Lookup):
    """Allow fieldname__fes_like=... lookups in querysets."""

    lookup_name = "fes_like"

    def as_sql(self, compiler, connection):
        """Generate the required SQL."""
        # lhs = "table"."field"
        # rhs = %s
        # lhs_params = []
        # lhs_params = ["prep-value"]
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        return f"{lhs} LIKE {rhs}", lhs_params + rhs_params

    def get_db_prep_lookup(self, value, connection):
        """This expects that the right-hand-side already has wildcard characters."""
        return "%s", [value]


@models.Field.register_lookup
class FesNotEqualTo(lookups.Lookup):
    """Allow fieldname__fes_notequal=... lookups in querysets."""

    lookup_name = "fes_notequal"

    def as_sql(self, compiler, connection):
        """Generate the required SQL."""
        lhs, lhs_params = self.process_lhs(compiler, connection)  # = (table.field, %s)
        rhs, rhs_params = self.process_rhs(compiler, connection)  # = ("prep-value", [])
        return f"{lhs} != {rhs}", lhs_params + rhs_params


@BaseSpatialField.register_lookup
class FesNotDWithinLookup(DistanceLookupBase):
    lookup_name = "fes_not_dwithin"
    sql_template = "NOT %(func)s(%(lhs)s, %(rhs)s, %(value)s)"
