import operator
from functools import reduce

from django.db import models
from django.db.models import Q, QuerySet, lookups


class FesQuery:
    """Collect all filters for a Django queryset."""

    def __init__(self, lookups=None, annotations=None):
        self.lookups = lookups or []
        self.annotations = annotations or {}
        self.aliases = 0
        self.extra_lookups = []

    def add_annotation(self, value):
        self.aliases += 1
        name = f"a{self.aliases}"
        self.annotations[name] = value
        return name

    def add_lookups(self, q_object: Q):
        if not isinstance(q_object, Q):
            raise TypeError()
        self.lookups.append(q_object)

    def add_extra_lookup(self, q_object: Q):
        """Temporary stash an extra lookup that the expression can't return yet."""
        if not isinstance(q_object, Q):
            raise TypeError()
        self.extra_lookups.append(q_object)

    def combine_extra_lookups(self, result: Q) -> Q:
        """Combine stashed lookups with the produced result."""
        if self.extra_lookups:
            result = reduce(operator.and_, [result] + self.extra_lookups)
            self.extra_lookups.clear()
        return result

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        """Apply the filters and lookups to the queryset"""
        if self.extra_lookups:
            # When
            raise RuntimeError("combine_extra_lookups() was not called")

        return queryset.annotate(**self.annotations).filter(*self.lookups)

    def __repr__(self):
        return f"<FesQuery annotations={self.annotations!r}, lookups={self.lookups!r}>"

    def __eq__(self, other):
        if isinstance(other, FesQuery):
            return (
                other.lookups == self.lookups and other.annotations == self.annotations
            )
        else:
            return NotImplemented


@models.CharField.register_lookup
@models.TextField.register_lookup
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


@models.CharField.register_lookup
@models.TextField.register_lookup
@models.DateField.register_lookup
@models.DateTimeField.register_lookup
class FesNotEqualTo(lookups.Lookup):
    """Allow fieldname__fes_notequal=... lookups in querysets."""

    lookup_name = "fes_notequal"

    def as_sql(self, compiler, connection):
        """Generate the required SQL."""
        lhs, lhs_params = self.process_lhs(compiler, connection)  # = (table.field, %s)
        rhs, rhs_params = self.process_rhs(compiler, connection)  # = ("prep-value", [])
        return f"{lhs} != {rhs}", lhs_params + rhs_params
