"""Additional ORM lookups used by the fes-filter code."""

from __future__ import annotations

from django.contrib.gis.db.models.fields import BaseSpatialField
from django.contrib.gis.db.models.lookups import DWithinLookup
from django.db import models
from django.db.models import lookups

from gisserver.compat import ArrayField


@models.CharField.register_lookup
@models.TextField.register_lookup
@models.ForeignObject.register_lookup
class FesLike(lookups.Lookup):
    """Allow ``fieldname__fes_like=...`` lookups in querysets."""

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
    """Allow ``fieldname__fes_notequal=...`` lookups in querysets."""

    lookup_name = "fes_notequal"

    def as_sql(self, compiler, connection):
        """Generate the required SQL."""
        lhs, lhs_params = self.process_lhs(compiler, connection)  # = (table.field, %s)
        rhs, rhs_params = self.process_rhs(compiler, connection)  # = ("prep-value", [])
        return f"{lhs} != {rhs}", (lhs_params + rhs_params)


@BaseSpatialField.register_lookup
class FesBeyondLookup(DWithinLookup):
    """Allow ``fieldname__fes_beyond=...`` lookups in querysets.

    Based on the FES 2.0.3 corrigendum:

    * ``DWithin(A,B,d) = Distance(A,B) < d``
    * ``Beyond(A,B,d) = Distance(A,B) > d``

    See: https://docs.opengeospatial.org/is/09-026r2/09-026r2.html#61
    """

    lookup_name = "fes_beyond"
    sql_template = "NOT %(func)s(%(lhs)s, %(rhs)s, %(value)s)"

    def get_rhs_op(self, connection, rhs):
        # Allow the SQL $(func)s to be different from the ORM lookup name.
        # This uses ST_DWithin() on PostGIS
        return connection.ops.gis_operators["dwithin"]


if ArrayField is None:
    ARRAY_LOOKUPS = {}
else:
    # Comparisons with array fields go through a separate ORM lookup expression,
    # so these can check whether ANY element matches in the array.
    # This gives consistency between other repeated elements (e.g. M2M, reverse FK)
    # where the whole object is returned when one of the sub-objects match.
    ARRAY_LOOKUPS = {
        "exact": "fes_anyexact",
        "fes_notequal": "fes_anynotequal",
        "fes_like": "fes_anylike",
        "lt": "fes_anylt",
        "lte": "fes_anylte",
        "gt": "fes_anygt",
        "gte": "fes_anygte",
    }

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
    class FesArrayAnyNotEqual(lookups.Lookup):
        """Inequality test for a single item in the array"""

        lookup_name = "fes_anynotequal"

        def as_sql(self, compiler, connection):
            """Generate the required SQL."""
            lhs, lhs_params = self.process_lhs(compiler, connection)
            rhs, rhs_params = self.process_rhs(compiler, connection)
            return f"{rhs} != ANY({lhs})", (rhs_params + lhs_params)

    @ArrayField.register_lookup
    class FesArrayLike(FesLike):
        """Allow like lookups for array fields."""

        lookup_name = "fes_anylike"

        def as_sql(self, compiler, connection):
            """Generate the required SQL."""
            lhs, lhs_params = self.process_lhs(compiler, connection)  # = (table.field, %s)
            rhs, rhs_params = self.process_rhs(compiler, connection)  # = ("prep-value", [])
            return (
                f"EXISTS(SELECT 1 FROM unnest({lhs}) AS item WHERE item LIKE {rhs})",  # noqa: S608
                (lhs_params + rhs_params),
            )
