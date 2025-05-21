"""Storage and registry for stored queries.
These definitions follow the WFS spec.

By using the :attr:`stored_query_registry`, custom stored queries can be registered in this server.
Out of the box, only the mandatory built-in :class:`GetFeatureById` query is present.
"""

from __future__ import annotations

import typing
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import partial
from xml.etree.ElementTree import Element

from django.db.models import Q

from gisserver.exceptions import InvalidParameterValue, NotFound, OperationNotSupported
from gisserver.features import FeatureType
from gisserver.parsers import fes20
from gisserver.parsers.query import CompiledQuery
from gisserver.types import XsdTypes

if typing.TYPE_CHECKING:
    from gisserver.output import SimpleFeatureCollection

__all__ = (
    "GetFeatureById",
    "QueryExpressionText",
    "StoredQueryDescription",
    "StoredQueryRegistry",
    "stored_query_registry",
    "WFS_LANGUAGE",
    "FES_LANGUAGE",
)

#: The query body is a ``<wfs:Query>``.
WFS_LANGUAGE = "urn:ogc:def:queryLanguage:OGC-WFS::WFS_QueryExpression"
#: The query body is a ``<fes:Filter>``.
FES_LANGUAGE = "urn:ogc:def:queryLanguage:OGC-FES:Filter"


@dataclass
class QueryExpressionText:
    """Define the body of a stored query.

    This object type is defined in the WFS spec.
    It may contain a ``<wfs:Query>`` or ``<fes:Filter>`` element.
    """

    #: Which types the query will return.
    return_feature_types: list[str] | None = None
    #: The internal language of the query. Can be a WFS/FES-filter, or "python"
    language: str = FES_LANGUAGE
    #: Whether the implementation_text will be show or hidden from users.
    is_private: bool = True

    #: Body
    implementation_text: str | Element | None = None


@dataclass
class StoredQueryDescription:
    """WFS metadata of a stored query.
    This is based on the ``<wfs:StoredQueryDescription>`` element,
    and returned in ``DescribeStoredQueries``.

    While it's possible to define multiple :class:`QueryExpressionText` nodes
    as metadata to describe a query, there is still only one implementation.
    Note there is no 'typeNames=...' parameter for stored queries.
    Only direct parameters act as input.
    """

    #: The ID of the query
    id: str
    #: User-visible title
    title: str
    #: User-visible description
    abstract: str
    #: Parameter declaration
    parameters: dict[str, XsdTypes]

    #: Metadata describing the query body
    expressions: list[QueryExpressionText] = field(
        default_factory=lambda: [QueryExpressionText(language=FES_LANGUAGE)]
    )

    #: Python-based implementation for the query.
    implementation_class: type[StoredQueryImplementation] = field(init=False, default=None)


class StoredQueryImplementation:
    """A custom stored query.

    This receives the parameters as init arguments,
    and should implement :meth:`build_query`.
    The function is registered using ``StoredQueryRegistry.register()``.
    """

    # Registered metadata
    _meta: StoredQueryDescription

    # Allow queries to return only the XML nodes, without any <wfs:FeatureCollection> wrapper.
    has_standalone_output: bool = False

    def __repr__(self):
        return f"<{self.__class__.__name__} implementing '{self._meta.id}'>"

    def bind(self, source_query, feature_types: list[FeatureType]):
        """Associate this query with the application data."""
        self.source_query = source_query
        self.feature_types = feature_types
        if len(feature_types) > 1:
            raise OperationNotSupported("Join queries are not supported", locator="typeNames")

    def get_type_names(self) -> list[str]:
        """Tell which type names this query applies to."""
        raise NotImplementedError()

    def build_query(self, compiler: CompiledQuery) -> Q | None:
        """Contribute our filter expression to the internal query.

        This should add the filter expressions to the internal query compiler.
        The top-level ``<wfs:StoredQuery>`` object will add
        the ``<wfs:PropertyName>`` logic and other elements.
        """
        raise NotImplementedError()

    def finalize_results(self, result: SimpleFeatureCollection):
        """Hook to allow subclasses to inspect the results."""


class StoredQueryRegistry:
    """Registry of functions to be callable by ``<wfs:StoredQuery>`` and ``STOREDQUERY_ID=...``."""

    def __init__(self):
        self.stored_queries: dict[str, type(StoredQueryImplementation)] = {}

    def __bool__(self):
        return bool(self.stored_queries)

    def __iter__(self) -> Iterator[StoredQueryDescription]:
        return iter(self.stored_queries.values())

    def get_queries(self) -> Iterable[StoredQueryDescription]:
        """Find all descriptions for stored queries."""
        return self.stored_queries.values()

    def register(
        self,
        meta: StoredQueryDescription | None = None,
        query_expression: type[StoredQueryImplementation] | None = None,
        **meta_kwargs,
    ):
        """Register a custom class that handles a stored query.
        This function can be used as decorator or normal call.
        """
        if meta is None:
            meta = StoredQueryDescription(**meta_kwargs)
        elif meta_kwargs:
            raise TypeError("Either provide the 'meta' object or 'meta_kwargs'")

        if query_expression is not None:
            return self._register(meta, query_expression)
        else:
            return partial(self._register, meta)  # decorator effect.

    def _register(
        self, meta: StoredQueryDescription, implementation_class: type[StoredQueryImplementation]
    ):
        """Internal registration method."""
        if not issubclass(implementation_class, StoredQueryImplementation):
            raise TypeError(f"Expecting {StoredQueryImplementation}' subclass")
        if meta.implementation_class is not None:
            raise RuntimeError("Can't register same StoredQueryDescription again.")

        # for now link both. There is always a single implementation for the metadata.
        meta.implementation_class = implementation_class
        self.stored_queries[meta.id] = meta
        return implementation_class  # for decorator usage

    def resolve_query(self, query_id) -> type[StoredQueryDescription]:
        """Find the stored procedure using the ID."""
        try:
            return self.stored_queries[query_id]
        except KeyError:
            raise InvalidParameterValue(
                f"Stored query does not exist: {query_id}",
                locator="STOREDQUERY_ID",
            ) from None


#: The stored query registry
stored_query_registry = StoredQueryRegistry()


@stored_query_registry.register(
    id="urn:ogc:def:query:OGC-WFS::GetFeatureById",
    title="Get feature by identifier",
    abstract="Returns the single feature that corresponds with the ID argument",
    parameters={"id": XsdTypes.string},
    expressions=[QueryExpressionText(language=WFS_LANGUAGE)],
)
class GetFeatureById(StoredQueryImplementation):
    """The stored query for GetFeatureById.

    This can be called using::

        <wfs:StoredQuery id="urn:ogc:def:query:OGC-WFS::GetFeatureById">
            <wfs:Parameter name="ID">typename.ID</wfs:Parameter>
        </wfs:StoredQuery>

    or using KVP syntax::

        ?...&REQUEST=GetFeature&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById&ID=typename.ID

    The execution of the ``GetFeatureById`` query is essentially the same as::

        <wfs:Query xmlns:wfs="..." xmlns:fes="...'>
          <fes:Filter><fes:ResourceId rid='{ID}'/></fes:Filter>
        </wfs:Query>

    or::

        <wfs:Query typeName="{typename}">
          <fes:Filter>
            <fes:PropertyIsEqualTo>
              <fes:ValueReference>{primary-key-field}</fes:ValueReference>
              <fes:Literal>{ID-value}</fes:Literal>
            </fes:PropertyIsEqualTo>
          </fes:Filter>
        </wfs:Query>

    Except that the response is supposed to contain only the item itself.
    """

    # Projection of GetFeatureById only returns the document nodes, not a <wfs:FeatureCollection> wrapper
    has_standalone_output = True

    def __init__(self, id: str, ns_aliases: dict[str, str]):
        """Initialize the query with the request parameters."""
        if "." not in id:
            # Always report this as 404
            raise NotFound("Expected typeName.id for ID parameter", locator="ID") from None

        # GetFeatureById is essentially a ResourceId lookup, reuse that logic here.
        self.resource_id = fes20.ResourceId.from_string(id, ns_aliases)

    def get_type_names(self) -> list[str]:
        """Tell which type names this query applies to."""
        return [self.resource_id.get_type_name()]

    def build_query(self, compiler: CompiledQuery) -> Q:
        """Contribute our filter expression to the internal query."""
        try:
            return self.resource_id.build_query(compiler)
        except InvalidParameterValue as e:
            raise InvalidParameterValue(f"Invalid ID value: {e.__cause__}", locator="ID") from e

    def finalize_results(self, results: SimpleFeatureCollection):
        """Override to implement 404 checking."""
        # Directly attempt to collect the data.
        # Avoid having to do that in the output renderer.
        if results.first() is None:
            # WFS 2.0.2: Return NotFound instead of InvalidParameterValue
            raise NotFound(f"Feature not found with ID {self.resource_id.rid}.", locator="ID")
