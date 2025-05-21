"""Handle (stored)query objects.

These definitions follow the WFS spec.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, ClassVar

from gisserver.exceptions import (
    ExternalParsingError,
    InvalidParameterValue,
    MissingParameterValue,
)
from gisserver.extensions.queries import (
    StoredQueryDescription,
    StoredQueryImplementation,
    stored_query_registry,
)
from gisserver.parsers.ast import tag_registry
from gisserver.parsers.ows import KVPRequest
from gisserver.parsers.query import CompiledQuery
from gisserver.parsers.xml import NSElement, xmlns
from gisserver.projection import FeatureProjection

from .base import QueryExpression

if typing.TYPE_CHECKING:
    from gisserver.output import SimpleFeatureCollection

__all__ = ("StoredQuery",)

# Fully qualified tag names
WFS_PARAMETER = xmlns.wfs20.qname("Parameter")


@dataclass
@tag_registry.register("StoredQuery", xmlns.wfs)
class StoredQuery(QueryExpression):
    """The ``<wfs:StoredQuery>`` element.

    This loads a predefined query on the server.
    A good description can be found at:
    https://mapserver.org/ogc/wfs_server.html#stored-queries-wfs-2-0

    This parses the following syntax::

        <wfs:StoredQuery handle="" id="">
          <wfs:Parameter name="">...</wfs:Parameter>
          <wfs:Parameter name="">...</wfs:Parameter>
        </wfs:StoredQuery>

    and the KVP syntax::

        ?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&STOREDQUERY_ID=...&{parameter}=...

    Note that the base class logic (such as ``<wfs:PropertyName>`` elements) are still applicable.

    This element resolves the stored query using the
    :class:`~gisserver.extensions.queries.StoredQueryRegistry`,
    and passes the execution to this custom function.
    """

    query_locator: ClassVar[str] = "STOREDQUERY_ID"

    id: str
    parameters: dict[str, Any]
    ns_aliases: dict[str, str] = field(compare=False, default_factory=dict)

    @classmethod
    def from_kvp_request(cls, kvp: KVPRequest):
        """Parse the KVP request syntax. Any query parameters are additional parameters at the query string."""
        query_id = kvp.get_str("STOREDQUERY_ID")
        query_description = stored_query_registry.resolve_query(query_id)
        raw_values = {
            # Take the value when it's there. No validation is done yet,
            # as those error messages are nicer in _parse_parameters()
            name: kvp.get_str(name)
            for name in query_description.parameters
            if name in kvp
        }

        # Avoid unexpected behavior, check whether the client also sends adhoc query parameters
        uc_args = [name.upper() for name in raw_values]
        for name in ("filter", "bbox", "resourceID"):
            uc_name = name.upper()
            if uc_name not in uc_args and uc_name in kvp:
                raise InvalidParameterValue(
                    "Stored query can't be combined with adhoc-query parameters", locator=name
                )

        return cls(
            id=query_id,
            parameters=cls._parse_parameters(query_description, raw_values),
            ns_aliases=kvp.ns_aliases,
        )

    @classmethod
    def from_xml(cls, element: NSElement):
        """Read the XML element."""
        query_id = element.get_str_attribute("id")
        query_description = stored_query_registry.resolve_query(query_id)
        raw_values = {
            parameter.get_str_attribute("name"): parameter.text
            for parameter in element.findall(WFS_PARAMETER)
        }
        return cls(
            id=query_id,
            parameters=cls._parse_parameters(query_description, raw_values),
            ns_aliases=element.ns_aliases,
        )

    @classmethod
    def _parse_parameters(
        cls, query_description: StoredQueryDescription, raw_values: dict[str, str]
    ) -> dict[str, Any]:
        """Validate and translate the incoming parameter.
        This transforms the raw values into their Python types.
        It also validates whether ll expected parameters are provided.
        """
        values = {}
        for name, xsd_type in query_description.parameters.items():
            try:
                raw_value = raw_values.pop(name)
            except KeyError:
                raise MissingParameterValue(
                    f"Stored query {query_description.id} requires an '{name}' parameter",
                    locator=name,
                ) from None

            try:
                values[name] = xsd_type.to_python(raw_value)
            except ExternalParsingError as e:
                raise InvalidParameterValue(
                    f"Stored query {query_description.id} parameter '{name}' can't parse '{raw_value}' as {xsd_type}."
                ) from e

        # Anything left means more parameters were given
        if raw_values:
            names = ", ".join(raw_values)
            raise InvalidParameterValue(
                f"Stored query {query_description.id} does not support the parameter: '{names}'.",
                locator=next(iter(raw_values)),
            )

        return values

    @cached_property
    def implementation(self) -> StoredQueryImplementation:
        """Initialize the stored query from this request."""
        query_description = stored_query_registry.resolve_query(self.id)
        return query_description.implementation_class(
            **self.parameters, ns_aliases=self.ns_aliases
        )

    def bind(self, *args, **kwargs):
        """Associate this query with the application context."""
        super().bind(*args, **kwargs)
        self.implementation.bind(source_query=self, feature_types=self.feature_types)

    def build_query(self, compiler: CompiledQuery):
        """Forward queryset creation to the implementation class."""
        return self.implementation.build_query(compiler)

    def as_kvp(self) -> dict:
        """Translate the POST request into KVP GET parameters. This is needed for pagination."""
        # As this is such edge case, only support the minimal for CITE tests.
        params = super().as_kvp()
        params["STOREDQUERY_ID"] = self.id
        for name, value in self.parameters.items():
            params[name] = str(value)  # should be raw value, but good enough for now.
        return params

    def get_type_names(self) -> list[str]:
        """Tell which features are touched by the query."""
        return self.implementation.get_type_names()

    def get_projection(self) -> FeatureProjection:
        """Tell how the <wfs:StoredQuery> output should be displayed."""
        return FeatureProjection(
            self.feature_types,
            self.property_names,
            value_reference=self.value_reference,
            # In the spec, it's not possible to change the output CRS of a stored query:
            # output_crs=self.srsName,
            output_standalone=self.implementation.has_standalone_output,  # for GetFeatureById
        )

    def finalize_results(self, result: SimpleFeatureCollection):
        return self.implementation.finalize_results(result)
