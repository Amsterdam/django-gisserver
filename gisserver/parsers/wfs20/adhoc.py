"""Handle adhoc-query objects.

The adhoc query is based on incoming request parameters,
such as the "FILTER", "BBOX" and "RESOURCEID" parameters.

These definitions follow the WFS spec.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cached_property

from django.db.models import Q

from gisserver.crs import CRS
from gisserver.exceptions import (
    InvalidParameterValue,
    MissingParameterValue,
    OperationNotSupported,
)
from gisserver.parsers import fes20
from gisserver.parsers.ast import tag_registry
from gisserver.parsers.ows import KVPRequest
from gisserver.parsers.query import CompiledQuery
from gisserver.parsers.xml import NSElement, xmlns
from gisserver.projection import FeatureProjection

from .base import QueryExpression
from .projection import PropertyName

logger = logging.getLogger(__name__)

ADHOC_QUERY_ELEMENTS = (PropertyName, fes20.Filter, fes20.SortBy)


@dataclass
@tag_registry.register("Query", xmlns.wfs)
class AdhocQuery(QueryExpression):
    """The Ad hoc query expression parameters.

    This parses and handles the syntax::

        <wfs:Query typeNames="...">
            <wfs:PropertyName>...</wfs:PropertyName>
            <fes:Filter>...</fes:Filter>
            <fes:SortBy>...</fes:SortBy>
        </wfs:Query>

    And supports the KVP syntax:

    .. code-block:: urlencoded

        ?SERVICE=WFS&...&TYPENAMES=ns:myType&FILTER=...&SORTBY=...&SRSNAME=...&PROPERTYNAME=...
        ?SERVICE=WFS&...&TYPENAMES=ns:myType&BBOX=...&SORTBY=...&SRSNAME=...&PROPERTYNAME=...
        ?SERVICE=WFS&...&TYPENAMES=ns:myType&RESOURCEID=...

    This represents all dynamic queries received as request (hence "adhoc"),
    such as the "FILTER" and "BBOX" arguments from an HTTP GET.

    The WFS Spec has 3 class levels for this:

     - AdhocQueryExpression (types, projection, selection, sorting)
     - Query (adds srsName, featureVersion)
     - StoredQuery (adds storedQueryID)

    For KVP requests, this class seems almost identifical to the provided parameters.
    However, the KVP format allows to provide parameter lists,
    to perform support multiple queries in a single request!

    .. seealso::
        https://www.mediamaps.ch/ogc/schemas-xsdoc/sld/1.2/query_xsd.html#AbstractAdhocQueryExpressionType
    """

    # Tag attributes (implements ``fes:AbstractAdhocQueryExpression``)
    # WFS allows multiple names to construct JOIN queries.
    # See https://docs.ogc.org/is/09-025r2/09-025r2.html#107
    # and https://docs.ogc.org/is/09-025r2/09-025r2.html#190

    #: The 'typeNames' value if the request provided them. use :meth:`get_type_names` instead.
    typeNames: list[str]
    #: Aliases for typeNames are used for joining the same table twice. (JOIN statements are not supported yet).
    aliases: list[str] | None = None
    #: For XML POST requests, this handle value is returned in the ``<ows:Exception>``.
    handle: str = ""

    # part of the <wfs:Query> tag attributes:
    #: The Coordinate Reference System to render the tag in
    srsName: CRS | None = None

    #: Projection clause (implements ``fes:AbstractProjectionClause``)
    property_names: list[PropertyName] | None = None

    #: Selection clause (implements ``fes:AbstractSelectionClause``).
    #: - for XML POST this is encoded in a <fes:Filter> tag.
    #: - for HTTP GET, this is encoded as FILTER, FILTER_LANGUAGE, RESOURCEID, BBOX.
    filter: fes20.Filter | None = None

    #: Sorting Clause (implements ``fes:AbstractSortingClause``)
    sortBy: fes20.SortBy | None = None

    def __post_init__(self):
        if len(self.typeNames) > 1:
            raise OperationNotSupported("Join queries are not supported", locator="typeNames")
        if self.aliases:
            raise OperationNotSupported("Join queries are not supported", locator="aliases")

    @classmethod
    def from_xml(cls, element: NSElement) -> AdhocQuery:
        """Parse the XML element of the Query tag."""
        type_names = [
            element.parse_qname(qname)
            for qname in element.get_str_attribute("typeNames").split(" ")
        ]
        aliases = element.attrib.get("aliases", None)
        srsName = element.attrib.get("srsName", None)
        property_names = []
        filter = None
        sortBy = None

        for child in element:
            # The FES XSD dictates the element ordering, but this is ignored here.
            node = tag_registry.node_from_xml(child, allowed_types=ADHOC_QUERY_ELEMENTS)
            if isinstance(node, PropertyName):
                property_names.append(node)
            elif isinstance(node, fes20.Filter):
                filter = node
            elif isinstance(node, fes20.SortBy):
                sortBy = node
            else:
                raise NotImplementedError(
                    f"Parsing {node.__class__} not handled in AdhocQuery.from_xml()"
                )

        return AdhocQuery(
            typeNames=type_names,
            aliases=aliases.split(" ") if aliases is not None else None,
            handle=element.attrib.get("handle", ""),
            property_names=property_names or None,
            filter=filter,
            sortBy=sortBy,
            srsName=CRS.from_string(srsName) if srsName else None,
        )

    @classmethod
    def from_kvp_request(cls, kvp: KVPRequest):
        """Build this object from an HTTP GET (key-value-pair) request.

        Note the caller should have split the KVP request parameter lists.
        This class only handles a single parameter pair.
        """
        # Parse attributes
        typeNames = [
            kvp.parse_qname(qname)
            for qname in kvp.get_list("typeNames", alias="TYPENAME", default=[])
        ]
        aliases = kvp.get_list("aliases", default=None)
        srsName = kvp.get_custom("srsName", default=None, parser=CRS.from_string)

        # KVP requests may omit the typenames if RESOURCEID=... is given.
        if not typeNames and "RESOURCEID" not in kvp:
            raise MissingParameterValue("Empty TYPENAMES parameter", locator="typeNames")

        # Parse elements
        filter = fes20.Filter.from_kvp_request(kvp)
        sort_by = fes20.SortBy.from_kvp_request(kvp)

        # Parse projection
        property_names = None
        if "PROPERTYNAME" in kvp:
            names = kvp.get_list("propertyName", default=[])
            # Check for WFS 1.x syntax of ?PROPERTYNAME=*
            if names != ["*"]:
                property_names = [
                    PropertyName(xpath=name, xpath_ns_aliases=kvp.ns_aliases) for name in names
                ]

        return AdhocQuery(
            # Attributes
            typeNames=typeNames,
            aliases=aliases,
            srsName=srsName,
            # Elements
            property_names=property_names,
            filter=filter,
            sortBy=sort_by,
        )

    @cached_property
    def query_locator(self):
        """Overrides the 'query_locator' attribute, so the 'locator' argument is correctly set."""
        if self.filter is not None and self.filter.get_resource_id_types():
            return "resourceId"
        else:
            return "filter"

    def get_type_names(self) -> list[str]:
        """Tell which type names this query uses.
        Multiple values means a JOIN is made (not supported yet).
        """
        if not self.typeNames and self.filter is not None:
            # Also make the behavior consistent, always supply the type name.
            return self.filter.get_resource_id_types() or []
        else:
            return self.typeNames

    def get_projection(self) -> FeatureProjection:
        """Tell how the ``<wfs:Query>`` element should be displayed."""
        return FeatureProjection(
            self.feature_types,
            self.property_names,
            self.value_reference,
            output_crs=self.srsName,
        )

    def bind(self, *args, **kwargs):
        """Override to make sure the 'locator' points to the actual object that defined the type."""
        try:
            super().bind(*args, **kwargs)
        except InvalidParameterValue as e:
            if not self.typeNames:
                e.locator = "resourceId"
            raise

        # Validate the srsName too
        if self.srsName is not None:
            self.srsName = self.feature_types[0].resolve_crs(self.srsName, locator="srsName")

    def build_query(self, compiler: CompiledQuery) -> Q | None:
        """Apply our collected filter data to the compiler."""
        # Add the sorting
        if self.sortBy is not None:
            self.sortBy.build_ordering(compiler)

        if self.filter is not None:
            # Generate the internal query object from the <fes:Filter>,
            # this can return a Q object.
            return self.filter.build_query(compiler)
        else:
            return None

    def as_kvp(self) -> dict:
        """Translate the POST request into KVP GET parameters. This is needed for pagination."""
        params = super().as_kvp()
        params["TYPENAMES"] = ",".join(self.typeNames)
        if self.srsName is not None:
            params["SRSNAME"] = str(self.srsName)

        if self.filter is not None:
            raise NotImplementedError()  # not going to parse that, nor does mapserver
        if self.sortBy is not None:
            params["SORTBY"] = self.sortBy.as_kvp()

        return params
