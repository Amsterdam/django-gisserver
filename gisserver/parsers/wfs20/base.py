"""Entry point to handle queries.

WFS defines 2 query types:
- Adhoc queries are constructed directly from request parameters.
- Stored queries are defined first, and executed later.

Both use the FES (Filter Encoding Syntax) filtering logic internally.

The objects in this module closely follow the WFS spec.
By using the same type definitions, a lot of code logic follows naturally.
"""

from __future__ import annotations

from typing import ClassVar

from django.db.models import Q, QuerySet

from gisserver.exceptions import (
    ExternalValueError,
    InvalidParameterValue,
    OperationNotSupported,
)
from gisserver.features import FeatureType
from gisserver.parsers import fes20, wfs20
from gisserver.parsers.ast import AstNode
from gisserver.parsers.query import CompiledQuery
from gisserver.projection import FeatureProjection


class QueryExpression(AstNode):
    """WFS base class for all queries.
    This object type is defined in the WFS spec (as ``<fes:AbstractQueryExpression>``).

    The WFS server can initiate queries in multiple ways.
    This class provides the common interface for all these query types;
    whether the request provided "ad-hoc" parameters or called a stored procedure.
    Each query type has its own way of generating the actual database statement to perform.

    The subclasses can override the following logic:

    * :meth:`get_type_names` defines which types this query applies to.
    * :meth:`build_query` defines how to filter the queryset.

    For full control, these methods can also be overwritten instead:

    * :meth:`get_queryset` defines the full results.
    """

    #: Configuration for the 'locator' argument in exceptions
    query_locator: ClassVar[str] = None

    # QueryExpression
    #: The 'handle' that will be returned in exceptions.
    handle: str = ""

    #: Projection parameters (overwritten by subclasses)
    #: In the WFS spec, this is only part of the operation/presentation.
    #: For Django, we'd like to make this part of the query too.
    property_names: list[wfs20.PropertyName] | None = None  # PropertyName

    #: The valueReference for the GetPropertyValue call, provided here for extra ORM filtering.
    value_reference: fes20.ValueReference | None = None

    def bind(
        self,
        feature_types: list[FeatureType],
        value_reference: fes20.ValueReference | None = None,
    ):
        """Bind the query to context outside its tag definition.

        :param feature_types: The corresponding feature types for :meth:`get_type_names`.
        :param value_reference: Which field is returned (by ``GetPropertyValue``)
        """
        # Store the resolved feature types
        self.feature_types = feature_types

        # for GetPropertyValue
        if value_reference is not None:
            self.value_reference = value_reference

    def get_queryset(self) -> QuerySet:
        """Generate the queryset for the specific feature type.

        This method can be overwritten in subclasses to define the returned data.
        However, consider overwriting :meth:`build_query` instead of simple data.
        """
        if len(self.feature_types) > 1:
            raise OperationNotSupported("Join queries are not supported", locator="typeNames")

        # To apply the filters, an internal CompiledQuery object is created.
        # This collects all steps, to create the final QuerySet object.
        # The build_query() method may return an Q object, or fill the compiler itself.
        compiler = CompiledQuery(self.feature_types)
        q_object = self.build_query(compiler)
        if q_object is not None:
            compiler.add_lookups(q_object)

        # While property names are projection, this hook should
        # make it possible to perform extra query adjustments for complex expressions.
        if self.property_names:
            for property_name in self.property_names:
                property_name.decorate_query(compiler)

        if self.value_reference is not None:
            try:
                self.value_reference.parse_xpath(self.feature_types)
            except ExternalValueError as e:
                raise InvalidParameterValue(
                    f"Field '{self.value_reference.xpath}' does not exist.",
                    locator="valueReference",
                ) from e

            # For GetPropertyValue, adjust the query so only that value is requested.
            # This makes sure XPath attribute selectors are already handled by the
            # database query, instead of being a presentation-layer handling.
            # This supports cases like: ``addresses/Address[street="Oxfordstrasse"]/number``
            field = self.value_reference.build_rhs(compiler)

            queryset = compiler.get_queryset()
            return queryset.values("pk", member=field)
        else:
            return compiler.get_queryset()

    def get_type_names(self) -> list[str]:
        """Tell which type names this query applies to.
        Multiple values means a JOIN is made (not supported yet).

        This method needs to be defined in subclasses.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.get_type_names() should be implemented."
        )

    def get_projection(self) -> FeatureProjection:
        """Tell how the query should be displayed."""
        raise NotImplementedError()

    def build_query(self, compiler: CompiledQuery) -> Q | None:
        """Define the compiled query that filters the queryset."""
        raise NotImplementedError()

    def as_kvp(self) -> dict:
        """Translate the POST request into KVP GET parameters. This is needed for pagination."""
        params = {}
        if self.property_names:
            params["PROPERTYNAME"] = ",".join(p.xpath for p in self.property_names)
        return params
