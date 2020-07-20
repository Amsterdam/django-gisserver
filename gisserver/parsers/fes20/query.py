import operator
from functools import reduce
from typing import Dict, List, Optional, Union

from django.contrib.gis.db.models.fields import BaseSpatialField
from django.contrib.gis.db.models.lookups import DistanceLookupBase
from django.db import models
from django.db.models import Q, QuerySet, lookups
from django.db.models.expressions import Combinable

from gisserver.features import FeatureType
from . import expressions, sorting


class CompiledQuery:
    """Intermediate data for translating FES queries to Django.

    This class contains all data from the ``<fes:Filter>`` object in a model
    that can be translated to a django QuerySet.

    This object is passed though all build_...() methods,
    so it can be used to add extra lookups and annotations.
    """

    def __init__(
        self,
        feature_type: Optional[FeatureType] = None,
        using: Optional[str] = None,
        lookups: Optional[List[Q]] = None,
        typed_lookups: Optional[Dict[str, List[Q]]] = None,
        annotations: Optional[Dict[str, Union[Combinable, Q]]] = None,
    ):
        """The init method is typically used only in unit tests."""
        self.feature_type = feature_type
        self.using = using
        self.lookups = lookups or []
        self.typed_lookups = typed_lookups or {}
        self.annotations = annotations or {}
        self.aliases = 0
        self.extra_lookups = []
        self.ordering = []
        self.is_empty = False

    def add_annotation(self, value: Union[Combinable, Q]) -> str:
        """Create an named-alias for a function/Q object.

        This alias can be used as left-hand-side of the query expression.
        """
        self.aliases += 1
        name = f"a{self.aliases}"
        self.annotations[name] = value
        return name

    def add_lookups(self, q_object: Q, type_name: Optional[str] = None):
        """Register an extra 'WHERE' clause of the query."""
        if not isinstance(q_object, Q):
            raise TypeError()

        if type_name is not None:
            if type_name not in self.typed_lookups:
                self.typed_lookups[type_name] = []
            self.typed_lookups[type_name].append(q_object)
        else:
            self.lookups.append(q_object)

    def add_extra_lookup(self, q_object: Q):
        """Temporary stash an extra lookup that the expression can't return yet."""
        if not isinstance(q_object, Q):
            raise TypeError()
        self.extra_lookups.append(q_object)

    def add_sort_by(self, sort_by: sorting.SortBy):
        self.ordering += sort_by.build_ordering(self.feature_type)

    def add_value_reference(self, value_reference: expressions.ValueReference) -> str:
        """Add a reference that should be returned by the query.

        This includes the XPath expression to the query, in case that adds
        extra lookups. The name (or alias) is returned that can be used in the
         ``queryset.values()`` result. This is needed to support cases like
        these in the future: ``addresses/Address[street="Oxfordstrasse"]/number``
        """
        return value_reference.build_rhs(self)

    def apply_extra_lookups(self, result: Q) -> Q:
        """Combine stashed lookups with the produced result."""
        if self.extra_lookups:
            result = reduce(operator.and_, [result] + self.extra_lookups)
            self.extra_lookups.clear()
        return result

    def mark_empty(self):
        """Mark as returning no results."""
        self.is_empty = True

    def filter_queryset(
        self, queryset: QuerySet, feature_type: FeatureType
    ) -> QuerySet:
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
            queryset = queryset.filter(*lookups)

        if self.ordering:
            queryset = queryset.order_by(*self.ordering)

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


@models.CharField.register_lookup
@models.TextField.register_lookup
@models.ForeignObject.register_lookup
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
@models.ForeignObject.register_lookup
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
