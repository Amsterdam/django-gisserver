"""Handle (stored)query objects.

These definitions follow the WFS spec.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from gisserver.exceptions import InvalidParameterValue, MissingParameterValue, NotFound
from gisserver.features import FeatureType
from gisserver.operations.base import Parameter
from gisserver.output import FeatureCollection
from gisserver.parsers import fes20
from gisserver.parsers.query import CompiledQuery
from gisserver.types import XsdTypes

from .base import QueryExpression


class QueryExpressionText:
    """Define the body of a stored query.

    This object type is defined in the WFS spec.
    It may contain a wfs:Query or wfs:StoredQuery element.
    """

    return_feature_types: list[str] | None = None
    language: str = fes20.Filter.query_language
    is_private: bool = False


@dataclass
class StoredQueryDescription:
    """WFS metadata of a stored query.
    This object type is defined in the WFS spec.
    """

    id: str = None
    title: str | None = None
    abstract: str | None = None
    parameters: dict[str, XsdTypes] | None = None
    expressions: list = None  # TODO: support multiple body expressions


class StoredQuery(QueryExpression):
    """Base class for stored queries.

    This represents all predefined queries on the server.
    A good description can be found at:
    https://mapserver.org/ogc/wfs_server.html#stored-queries-wfs-2-0

    The implementation logic is fully defined by the :class:`QueryExpression`
    base class. For a simple implementation, the following data should be
    overwritten:

    * :meth:`get_type_names` to define which type this query references.
    * :meth:`compile_query` to define the queryset filter.

    For advanced overriding, see the :class:`QueryExpression` base class,
    or the :class:`GetFeatureById` implementation.
    """

    # Official WFS docs have an 'id' and 'parameters' property for the
    # StoredQuery class, but these are avoided here to give subclasses full
    # control over which properties to store. E.g. "id" conflicts with Django
    # model subclasses that stores the query.
    meta: StoredQueryDescription

    def __init__(self, **parameters):
        self.parameters = parameters

    @classmethod
    def extract_parameters(cls, KVP) -> dict[str, str]:
        """Extract the arguments from the key-value-pair (=HTTP GET) request."""
        args = {}
        for name, _xsd_type in cls.meta.parameters.items():
            try:
                args[name] = KVP[name]
            except KeyError:
                raise MissingParameterValue(
                    f"Stored query {cls.meta.id} requires an '{name}' parameter", locator=name
                ) from None

        # Avoid unexpected behavior, check whether the client also sends adhoc query parameters
        for name in ("filter", "bbox", "resourceID"):
            if name not in args and KVP.get(name.upper()):
                raise InvalidParameterValue(
                    "Stored query can't be combined with adhoc-query parameters", locator=name
                )

        return args


class StoredQueryRegistry:
    """Registry of functions to be callable by <fes:Query>."""

    def __init__(self):
        self.stored_queries = {}

    def __bool__(self):
        return bool(self.stored_queries)

    def __iter__(self):
        return iter(self.stored_queries.values())

    def register(self, meta: StoredQueryDescription | None = None, **meta_kwargs):
        """Register a custom class that handles a stored query"""

        def _metadata_dec(query: type[StoredQuery]):
            query.meta = meta or StoredQueryDescription(**meta_kwargs)
            self.stored_queries[query.meta.id] = query
            return query

        return _metadata_dec

    def resolve_query(self, query_id) -> type[StoredQuery]:
        """Find the stored procedure using the ID."""
        try:
            return self.stored_queries[query_id]
        except KeyError:
            raise InvalidParameterValue(
                f"Stored query does not exist: {query_id}",
                locator="STOREDQUERY_ID",
            ) from None


stored_query_registry = StoredQueryRegistry()


class StoredQueryParameter(Parameter):
    """Special parameter parsing for the 'STOREDQUERY_ID' parameter"""

    def __init__(self):
        super().__init__(name="STOREDQUERY_ID", parser=stored_query_registry.resolve_query)

    def value_from_query(self, KVP: dict):
        """Customize the request parsing to read custom parameters too."""
        stored_query_class = super().value_from_query(KVP)
        if stored_query_class is None:
            return None

        parameters = stored_query_class.extract_parameters(KVP)
        return stored_query_class(**parameters)


@stored_query_registry.register(
    id="urn:ogc:def:query:OGC-WFS::GetFeatureById",
    title="Get feature by identifier",
    abstract="Returns the single feature that corresponds with the ID argument",
    parameters={"ID": XsdTypes.string},
    # expressions=[QueryExpressionText],
)
class GetFeatureById(StoredQuery):
    """The stored query for GetFeatureById.

    This is essentially the same as:

    <wfs:Query xmlns:wfs='..." xmlns:fes='...'>
        <fes:Filter><fes:ResourceId rid='{ID}'/></fes:Filter>
    </wfs:Query>

    Except that the response is supposed to contain only the item itself.
    """

    def __init__(self, ID):
        """Initialize the query with the request parameters."""
        if "." not in ID:
            # Always report this as 404
            raise NotFound("Expected typeName.id for ID parameter", locator="ID") from None

        # GetFeatureById is essentially a ResourceId lookup, reuse that logic here.
        self.resource_id = fes20.ResourceId(rid=ID)

    def get_type_names(self) -> list[FeatureType]:
        """Tell which type names this query applies to."""
        type_name = self.resource_id.get_type_name()
        feature_type = self.all_feature_types[type_name]
        return [feature_type]

    def build_query(self, compiler: CompiledQuery) -> Q:
        """Contribute our filter expression to the internal query."""
        try:
            return self.resource_id.build_query(compiler)
        except InvalidParameterValue as e:
            raise InvalidParameterValue(f"Invalid ID value: {e.__cause__}", locator="ID") from e

    def get_results(self, *args, **kwargs) -> FeatureCollection:
        """Override to implement 404 checking."""
        collection = super().get_results(*args, **kwargs)

        # Directly attempt to collect the data.
        # Avoid having to do that in the output renderer.
        if collection.results[0].first() is None:
            # WFS 2.0.2: Return NotFound instead of InvalidParameterValue
            raise NotFound(f"Feature not found with ID {self.resource_id.rid}.", locator="ID")

        return collection
