from __future__ import annotations
import operator
from functools import reduce

from django.conf import settings
from django.contrib.gis.db.models.fields import BaseSpatialField
from django.contrib.gis.db.models.lookups import DWithinLookup
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
        feature_type: FeatureType | None = None,
        using: str | None = None,
        lookups: list[Q] | None = None,
        typed_lookups: dict[str, list[Q]] | None = None,
        annotations: dict[str, Combinable | Q] | None = None,
    ):
        """The init method is typically used only in unit tests."""
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

    def add_sort_by(self, sort_by: sorting.SortBy):
        """Read the desired result ordering from a ``<fes:SortBy>`` element."""
        self.ordering += sort_by.build_ordering(self.feature_type)

    def add_value_reference(self, value_reference: expressions.ValueReference) -> str:
        """Add a reference that should be returned by the query.

        This includes the XPath expression to the query, in case that adds
        extra lookups. The name (or alias) is returned that can be used in the
         ``queryset.values()`` result. This is needed to support cases like
        these in the future: ``addresses/Address[street="Oxfordstrasse"]/number``
        """
        return value_reference.build_rhs(self)

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
class FesNotEqual(lookups.Lookup):
    """Allow fieldname__fes_notequal=... lookups in querysets."""

    lookup_name = "fes_notequal"

    def as_sql(self, compiler, connection):
        """Generate the required SQL."""
        lhs, lhs_params = self.process_lhs(compiler, connection)  # = (table.field, %s)
        rhs, rhs_params = self.process_rhs(compiler, connection)  # = ("prep-value", [])
        return f"{lhs} != {rhs}", (lhs_params + rhs_params)


@BaseSpatialField.register_lookup
class FesBeyondLookup(DWithinLookup):
    """Based on the FES 2.0.3 corrigendum:

    DWithin(A,B,d) = Distance(A,B) < d
    Beyond(A,B,d) = Distance(A,B) > d

    See: https://docs.opengeospatial.org/is/09-026r2/09-026r2.html#61
    """

    lookup_name = "fes_beyond"
    sql_template = "NOT %(func)s(%(lhs)s, %(rhs)s, %(value)s)"

    def get_rhs_op(self, connection, rhs):
        # Allow the SQL $(func)s to be different from the ORM lookup name.
        # This uses ST_DWithin() on PostGIS
        return connection.ops.gis_operators["dwithin"]


if "django.contrib.postgres" in settings.INSTALLED_APPS:
    from django.contrib.postgres.fields import ArrayField

    class ArrayAnyMixin:
        any_operators = {
            "exact": "= ANY(%s)",
            "ne": "!= ANY(%s)",
            "gt": "< ANY(%s)",
            "gte": "<= ANY(%s)",
            "lt": "> ANY(%s)",
            "lte": ">= ANY(%s)",
        }

        def as_sql(self, compiler, connection):
            # For the ANY() comparison, the filter operands need to be reversed.
            # So instead of "field < value", it becomes "value > ANY(field)
            lhs_sql, lhs_params = self.process_lhs(compiler, connection)
            rhs_sql, rhs_params = self.process_rhs(compiler, connection)
            lhs_sql = self.get_rhs_op(connection, lhs_sql)
            return f"{rhs_sql} {lhs_sql}", (rhs_params + lhs_params)

        def get_rhs_op(self, connection, rhs):
            return self.any_operators[self.lookup_name] % rhs

    def _register_any_lookup(base: type[lookups.BuiltinLookup]):
        """Register array lookups under a different name."""
        cls = type(f"FesArrayAny{base.__name__}", (ArrayAnyMixin, base), {})
        ArrayField.register_lookup(cls, lookup_name=f"fes_any{base.lookup_name}")

    _register_any_lookup(lookups.Exact)
    _register_any_lookup(lookups.Exact)
    _register_any_lookup(lookups.GreaterThan)
    _register_any_lookup(lookups.GreaterThanOrEqual)
    _register_any_lookup(lookups.LessThan)
    _register_any_lookup(lookups.LessThanOrEqual)

    @ArrayField.register_lookup
    class FesArrayAnyNotEqual(FesNotEqual):
        """Inequality test for a single item in the array"""

        lookup_name = "fes_anynotequal"

        def as_sql(self, compiler, connection):
            """Generate the required SQL."""
            lhs, lhs_params = self.process_lhs(compiler, connection)
            rhs, rhs_params = self.process_rhs(compiler, connection)
            return f"{rhs} != ANY({lhs})", (rhs_params + lhs_params)
