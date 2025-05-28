"""WFS 2.0 request objects for parsing.

These objects convert the various request formats into a uniform request object.
The object properties are based on the WFS specification and XSD type names.
By following these definitions closely, it naturally follows to support nearly
all possible request formats outside the common examples.

Examples:

* https://schemas.opengis.net/wfs/2.0/examples/
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gisserver.exceptions import (
    InvalidParameterValue,
    MissingParameterValue,
    OperationParsingFailed,
)
from gisserver.parsers import fes20
from gisserver.parsers.ast import expect_no_children, tag_registry
from gisserver.parsers.ows import BaseOwsRequest, KVPRequest
from gisserver.parsers.xml import NSElement, xmlns

from .adhoc import AdhocQuery
from .base import QueryExpression
from .projection import ResolveValue, parse_resolve_depth
from .stored import StoredQuery

OWS_GET_CAPABILITIES_ELEMENTS = {
    # {"child-tag": ("item-tag", "python_name")}
    xmlns.ows11.qname("AcceptVersions"): (xmlns.ows11.qname("Version"), "acceptVersions"),
    xmlns.ows11.qname("Sections"): (xmlns.ows11.qname("Section"), "sections"),
    xmlns.ows11.qname("AcceptFormats"): (xmlns.ows11.qname("OutputFormat"), "acceptFormats"),
    xmlns.ows11.qname("AcceptLanguages"): (xmlns.ows11.qname("Language"), "acceptLanguages"),
}

# Fully qualified tag names
WFS_TYPE_NAME = xmlns.wfs20.qname("TypeName")
WFS_STORED_QUERY = xmlns.wfs20.qname("StoredQuery")


@dataclass
@tag_registry.register("GetCapabilities", xmlns.wfs20)
@tag_registry.register("GetCapabilities", xmlns.wfs1, hidden=True)  # to give negotiation error.
class GetCapabilities(BaseOwsRequest):
    """Request parsing for GetCapabilities.

    This parses and handles the syntax::

        <wfs:GetCapabilities service="WFS" updateSequence="" version="">
            <ows:AcceptVersions>
                <ows:Version>...</ows:Version>
            </ows:AcceptVersions>
            <ows:Sections>
                <ows:Section>...</ows:Section>
                <ows:Section>...</ows:Section>
            </ows:Sections>
            <ows:AcceptFormats>
                <ows:OutputFormat>...</ows:OutputFormat>
                <ows:OutputFormat>...</ows:OutputFormat>
            </ows:AcceptFormats>
            <ows:AcceptLanguages>
                <ows:Language>...</ows:Language>
                <ows:Language>...</ows:Language>
            </ows:AcceptLanguages>
        </wfs:GetCapabilities>

    And supports the GET syntax as well::

        ?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=2.0.0,1.1.0
    """

    updateSequence: str | None = None
    acceptVersions: list[str] | None = None
    # Sections can be: "ServiceIdentification", "ServiceProvider", "OperationsMetadata", "FeatureTypeList", "Filter_Capabilities"
    sections: list[str] | None = None
    acceptFormats: list[str] | None = None
    acceptLanguages: list[str] | None = None

    def __post_init__(self):
        # Even GetCapabilities can still receive a version argument to fixate it.
        if self.version and self.acceptVersions:
            raise InvalidParameterValue(
                "Can't provide both AcceptVersions and version", locator="AcceptVersions"
            )

    @classmethod
    def from_xml(cls, element: NSElement):
        """Parse the XML tag for the GetCapabilities."""
        ows_kwargs = {}
        for child in element:
            pair = OWS_GET_CAPABILITIES_ELEMENTS.get(child.tag)
            if pair is not None:
                item_tag, arg_name = pair
                ows_kwargs[arg_name] = [item.text for item in child.findall(item_tag)]

        return cls(
            # version is optional for this type, unlike all other methods
            # so not calling **cls.base_xml_init_parameters()
            service=element.get_str_attribute("service"),
            version=element.attrib.get("version"),
            handle=element.attrib.get("handle"),
            updateSequence=element.attrib.get("updateSequence", None),
            **ows_kwargs,
        )

    @classmethod
    def from_kvp_request(cls, kvp: KVPRequest):
        """Parse the KVP request format."""
        return cls(
            # version is optional for this type, unlike all other methods
            # so not calling **cls.base_kvp_init_parameters()
            service=kvp.get_str("SERVICE"),
            version=kvp.get_str("VERSION", default=None),
            handle=None,
            acceptVersions=kvp.get_list("AcceptVersions", default=None),
            acceptFormats=kvp.get_list("AcceptFormats", default=None),
            acceptLanguages=kvp.get_list("AcceptLanguages", default=None),
            sections=kvp.get_list("sections", default=None),
        )


@dataclass
@tag_registry.register("DescribeFeatureType", xmlns.wfs20)
class DescribeFeatureType(BaseOwsRequest):
    """The ``<wfs:DescribeFeatureType>`` element.

    This parses the syntax::

        <wfs:DescribeFeatureType version="2.0.0" service="WFS">
          <wfs:TypeName>ns01:TreesA_1M</wfs:TypeName>
          <wfs:TypeName>ns02:RoadL_1M</wfs:TypeName>
        </wfs:DescribeFeatureType>

    And supports the GET syntax as well::

        ?SERVICE=WFS&VERSION=2.0.0&REQUEST=DescribeFeatureType&TYPENAMES=ns01:TreesA_1M,ns02:RoadL_1M
    """

    typeNames: list[str] | None = None
    # WFS spec actually defines "application/gml+xml; version="3.2" as default output format value.
    outputFormat: str | None = "XMLSCHEMA"

    @classmethod
    def from_xml(cls, element: NSElement):
        """Parse the XML POST request."""
        type_name_tags = element.findall(WFS_TYPE_NAME)
        if any(not e.text for e in type_name_tags):
            raise MissingParameterValue("Missing TypeName value", locator="TypeName")

        return cls(
            **cls.base_xml_init_parameters(element),
            typeNames=[e.parse_qname(e.text) for e in type_name_tags] or None,
            outputFormat=element.attrib.get("outputFormat", "XMLSCHEMA"),
        )

    @classmethod
    def from_kvp_request(cls, kvp: KVPRequest):
        """Parse the KVP GET request"""
        type_names = (
            # Check for empty values, don't check for missing values:
            kvp.get_list("typeNames", alias="typename")
            if ("typeNames" in kvp or "typename" in kvp)
            else None
        )

        return cls(
            **cls.base_kvp_init_parameters(kvp),
            # TYPENAME is WFS 1.x, but some clients and the Cite test suite send it.
            typeNames=(
                [kvp.parse_qname(name) for name in type_names] if type_names is not None else None
            ),
            outputFormat=kvp.get_str("outputFormat", default="XMLSCHEMA"),
        )


class ResultType(Enum):
    """WFS result type format."""

    hits = "HITS"
    results = "RESULTS"

    @classmethod
    def _missing_(cls, value):
        raise OperationParsingFailed(f"Invalid resultType value: {value}", locator="resultType")


@dataclass
class StandardPresentationParameters(BaseOwsRequest):
    """Mixin that handles presentation parameters shared between different types.
    This element mirrors the ``wfs:StandardPresentationParameters`` type.
    """

    count: int | None = None
    outputFormat: str = "application/gml+xml; version=3.2"
    resultType: ResultType = ResultType.results
    startIndex: int = 0

    @classmethod
    def base_xml_init_parameters(cls, element: NSElement) -> dict:
        """Parse the XML POST request."""
        return dict(
            **super().base_xml_init_parameters(element),
            count=element.get_int_attribute("count"),
            outputFormat=element.attrib.get("outputFormat", "application/gml+xml; version=3.2"),
            resultType=ResultType[element.attrib.get("resultType", "results")],
            startIndex=element.get_int_attribute("startIndex", 0),
        )

    @classmethod
    def base_kvp_init_parameters(cls, kvp: KVPRequest) -> dict:
        """Parse the KVP GET request."""
        return dict(
            **super().base_kvp_init_parameters(kvp),
            # maxFeatures is WFS 1.x but some clients still send it.
            count=kvp.get_int("count", alias="maxFeatures", default=None),
            outputFormat=kvp.get_str("outputFormat", default="application/gml+xml; version=3.2"),
            resultType=ResultType[kvp.get_str("resultType", default="results").lower()],
            startIndex=kvp.get_int("startIndex", default=0),
        )

    def as_kvp(self) -> dict:
        """Translate the POST request into KVP GET parameters. This is needed for pagination."""
        params = super().as_kvp()
        if self.outputFormat != "application/gml+xml; version=3.2":
            params["OUTPUTFORMAT"] = self.outputFormat
        if self.resultType != ResultType.results:
            params["RESULTTYPE"] = self.resultType.value
        if self.startIndex:
            params["STARTINDEX"] = self.startIndex
        if self.count is not None:
            params["COUNT"] = self.count
        return params


@dataclass
class StandardResolveParameters(BaseOwsRequest):
    """Mixin that handles resolve parameters shared between different types.
    This element mirrors the ``wfs:StandardResolveParameters`` type.
    """

    resolve: ResolveValue = ResolveValue.none
    resolveDepth: int | None = None
    resolveTimeout: int = 300

    @classmethod
    def base_xml_init_parameters(cls, element: NSElement) -> dict:
        """Parse the XML POST request."""
        return dict(
            **super().base_xml_init_parameters(element),
            resolve=ResolveValue[element.attrib.get("resolve", "none")],
            resolveDepth=parse_resolve_depth(element.attrib.get("resolveDepth", None)),
            resolveTimeout=element.get_int_attribute("resolveTimeout", 300),
        )

    @classmethod
    def base_kvp_init_parameters(cls, kvp: KVPRequest) -> dict:
        """Parse the KVP GET request."""
        depth = kvp.get_str("resolveDepth", default="*")
        return dict(
            **super().base_kvp_init_parameters(kvp),
            resolve=ResolveValue[kvp.get_str("resolve", default="none")],
            resolveDepth=parse_resolve_depth(depth),
            resolveTimeout=kvp.get_int("resolveTimeout", default=300),
        )


@dataclass
class CommonQueryParameters(BaseOwsRequest):
    """Internal mixin to deal with the query parameters"""

    queries: list[QueryExpression] = None  # need default for inheritance

    @classmethod
    def base_xml_init_parameters(cls, element: NSElement):
        """Parse the XML POST request"""
        return dict(
            **super().base_xml_init_parameters(element),
            queries=[
                # This can instantiate an AdhocQuery or StoredQuery
                QueryExpression.child_from_xml(child)
                for child in element
            ],
        )

    @classmethod
    def base_kvp_init_parameters(cls, kvp: KVPRequest):
        """Parse the KVP GET request"""
        stored_query_id = kvp.get_str("STOREDQUERY_ID", default=None)
        if stored_query_id:
            queries = [
                StoredQuery.from_kvp_request(sub_request)
                for sub_request in kvp.split_parameter_lists()
            ]
        else:
            queries = [
                AdhocQuery.from_kvp_request(sub_request)
                for sub_request in kvp.split_parameter_lists()
            ]

        return dict(
            **super().base_kvp_init_parameters(kvp),
            queries=queries,
        )

    def as_kvp(self) -> dict:
        """Translate the POST request into KVP GET parameters. This is needed for pagination."""
        if len(self.queries) > 1:
            raise NotImplementedError()
        return {
            **super().as_kvp(),
            **self.queries[0].as_kvp(),
        }


@dataclass
@tag_registry.register("GetFeature", xmlns.wfs20)
class GetFeature(
    StandardPresentationParameters,
    StandardResolveParameters,
    CommonQueryParameters,
    BaseOwsRequest,
):
    """The ``<wfs:GetFeature>`` element.

    This parses the syntax::

        <wfs:GetFeature outputFormat="application/gml+xml; version=3.2">
           <wfs:Query typeName="myns:InWaterA_1M">
              <fes:Filter>
                  ...
              </fes:Filter>
           </wfs:Query>
        </wfs:GetFeature>

    And supports the KVP syntax::

        ?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=myns:InWaterA_1M&FILTER=...

    """


@dataclass
@tag_registry.register("GetPropertyValue", xmlns.wfs20)
class GetPropertyValue(
    StandardPresentationParameters,
    StandardResolveParameters,
    CommonQueryParameters,
    BaseOwsRequest,
):
    """The ``<wfs:GetPropertyValue>`` element.

    This parses the syntax::

        <wfs:GetPropertyValue valueReference="...">
           <wfs:Query typeName="myns:InWaterA_1M">
              <fes:Filter>
                  ...
              </fes:Filter>
           </wfs:Query>
        </wfs:GetFeature>

    As this is so similar to the :class:`GetFeature` syntax, these inherit from each other.

    The KVP-syntax is also supported::

        ?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetPropertyName&...&&VALUEREFERENCE=...
    """

    resolvePath: str | None = None
    valueReference: fes20.ValueReference = None  # need default for inheritance

    def __post_init__(self):
        if self.resolvePath:
            raise InvalidParameterValue(
                "Support for resolvePath is not implemented!", locator="resolvePath"
            )
        if len(self.queries) > 1:
            raise InvalidParameterValue(
                "GetPropertyValue only supports a single query", locator="filter"
            )

    @classmethod
    def from_xml(cls, element: NSElement):
        """Parse the XML POST request."""
        return cls(
            **cls.base_xml_init_parameters(element),
            resolvePath=element.attrib.get("resolvePath", None),
            valueReference=fes20.ValueReference(
                xpath=element.get_str_attribute("valueReference"),
                xpath_ns_aliases=element.ns_aliases,
            ),
        )

    @classmethod
    def from_kvp_request(cls, kvp: KVPRequest):
        """Parse the KVP GET request."""
        return cls(
            **cls.base_kvp_init_parameters(kvp),
            resolvePath=kvp.get_str("resolvePath", default=None),
            valueReference=fes20.ValueReference(
                xpath=kvp.get_str("valueReference"),
                xpath_ns_aliases=kvp.ns_aliases,
            ),
        )

    def as_kvp(self) -> dict:
        """Translate the POST request into KVP GET parameters. This is needed for pagination."""
        return {
            **super().as_kvp(),
            "VALUEREFERENCE": self.valueReference.xpath,
        }


@tag_registry.register("ListStoredQueries", xmlns.wfs20)
class ListStoredQueries(BaseOwsRequest):
    """The ``<wfs:ListStoredQueries>`` element."""

    @classmethod
    @expect_no_children
    def from_xml(cls, element: NSElement):
        return super().from_xml(element)


@dataclass
@tag_registry.register("DescribeStoredQueries", xmlns.wfs20)
class DescribeStoredQueries(BaseOwsRequest):
    """The ``<wfs:DescribeStoredQueries>`` element.

    This parses the syntax::

        <wfs:DescribeStoredQueries>
          <wfs:StoredQueryId>...</wfs:StoredQueryId>
          <wfs:StoredQueryId>...</wfs:StoredQueryId>
        </wfs:DescribeStoredQueries>

    And the KVP syntax::

        ?REQUEST=DescribeStoredQueries&STOREDQUERY_ID=...,...
    """

    storedQueryId: list[str] | None = None

    @classmethod
    def from_xml(cls, element: NSElement):
        """Parse the XML POST request."""
        id_tags = element.findall(WFS_STORED_QUERY)
        if any(not e.text for e in id_tags):
            raise MissingParameterValue("Missing StoredQuery value", locator="StoredQuery")

        return cls(
            **cls.base_xml_init_parameters(element),
            storedQueryId=[child.text for child in id_tags] or None,
        )

    @classmethod
    def from_kvp_request(cls, kvp: KVPRequest):
        """Parse the KVP GET request."""
        return cls(
            **cls.base_kvp_init_parameters(kvp),
            storedQueryId=kvp.get_list("STOREDQUERY_ID", default=None),
        )


# @tag_registry.register("CreateStoredQuery", xmlns.wfs20)
# class CreateStoredQuery(BaseRequest):
#     ...
#
# @tag_registry.register("LockFeature", xmlns.wfs20)
# class LockFeature(BaseRequest):
#     ...
#
# @tag_registry.register("TransactionType", xmlns.wfs20)
# class TransactionType(BaseRequest):
#     ...
#
# @tag_registry.register("DropStoredQuery", xmlns.wfs20)
# class DropStoredQuery(BaseRequest):
#     ...
