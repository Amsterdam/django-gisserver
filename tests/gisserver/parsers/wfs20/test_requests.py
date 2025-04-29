from urllib.parse import quote

import pytest

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers import fes20, wfs20
from gisserver.parsers.fes20.expressions import Literal
from gisserver.parsers.fes20.operators import (
    BinaryComparisonName,
    BinaryComparisonOperator,
    IdOperator,
)
from gisserver.parsers.ows import parse_get_request, parse_post_request
from gisserver.parsers.xml import xmlns
from tests.requests import Get, Post, parametrize_ows_request
from tests.utils import XML_NS, XML_NS_WFS


class TestListStoredQueries:
    """As this is a plain tag without elements, test this first.
    This also doesn't use @parametrize_ows_request to make internal testing easier.
    """

    def test_kvp(self):
        query_string = "?SERVICE=WFS&REQUEST=ListStoredQueries&VERSION=2.0.0"
        ows_request = parse_get_request(query_string)
        assert ows_request == wfs20.ListStoredQueries(service="WFS", version="2.0.0", handle=None)

    def test_xml(self):
        xml = f'<ListStoredQueries version="2.0.0" service="WFS" {XML_NS}></ListStoredQueries>'
        ows_request = parse_post_request(xml)
        assert ows_request == wfs20.ListStoredQueries(service="WFS", version="2.0.0", handle=None)

    @pytest.mark.parametrize("alias", ["wfs", "ns0"])
    def test_xml_alias(self, alias):
        """Prove that in general, XML aliases work fine"""
        xml = f'<{alias}:ListStoredQueries version="2.0.0" service="WFS" xmlns:{alias}="{xmlns.wfs}"></{alias}:ListStoredQueries>'
        ows_request = parse_post_request(xml)
        assert ows_request == wfs20.ListStoredQueries(service="WFS", version="2.0.0", handle=None)

    def test_unknown_alias(self):
        """Prove that invalid tag names are properly detected."""
        xml = '<ns0:ListStoredQueries version="2.0.0" service="WFS" xmlns:ns0="http://example.org/gisserver"></ns0:ListStoredQueries>'
        with pytest.raises(ExternalParsingError) as exc_info:
            parse_post_request(xml)

        message = exc_info.value.args[0]
        assert message.startswith(
            "Unsupported tag: <ns0:ListStoredQueries>,"
            " expected one of: <{http://www.opengis.net/wfs/2.0}GetCapabilities>,"
            " <{http://www.opengis.net/wfs/2.0}DescribeFeatureType>, "
        ), message


class TestGetCapabilities:
    """Test GetCapabilities parsing."""

    @parametrize_ows_request(
        Get("?SERVICE=WFS&REQUEST=GetCapabilities"),
        Post(f'<GetCapabilities service="WFS" {XML_NS}></GetCapabilities>'),
    )
    def test_minimal(self, ows_request):
        """Prove that the minimal request works, version is not required.."""
        assert ows_request == wfs20.GetCapabilities(service="WFS", version=None, handle=None)

    @parametrize_ows_request(
        Get("?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=1.0.0,2.0.0"),
        Post(
            f"""
            <GetCapabilities service="WFS" {XML_NS}>
              <ows:AcceptVersions>
                <ows:Version>1.0.0</ows:Version>
                <ows:Version>2.0.0</ows:Version>
              </ows:AcceptVersions>
            </GetCapabilities>"""
        ),
    )
    def test_accept_versions(self, ows_request):
        assert ows_request == wfs20.GetCapabilities(
            service="WFS",
            version=None,
            handle=None,
            acceptVersions=["1.0.0", "2.0.0"],
        )


class TestDescribeFeatureType:
    """Test DescribeFeatureType parsing."""

    @parametrize_ows_request(
        Get("?SERVICE=WFS&VERSION=2.0.0&REQUEST=DescribeFeatureType"),
        Post(
            f'<DescribeFeatureType version="2.0.0" service="WFS" {XML_NS}></DescribeFeatureType>'
        ),
    )
    def test_minimal(self, ows_request):
        assert ows_request == wfs20.DescribeFeatureType(
            service="WFS",
            version="2.0.0",
            handle=None,
            typeNames=None,
            outputFormat="XMLSCHEMA",
        )

    @parametrize_ows_request(
        Get("?SERVICE=WFS&VERSION=2.0.0&REQUEST=DescribeFeatureType&TYPENAMES=restaurant,place"),
        Post(
            # app:namespace
            f"""
            <DescribeFeatureType version="2.0.0" service="WFS"
                 xmlns="{xmlns.wfs}" xmlns:app="http://example.org/gisserver">
              <TypeName>app:restaurant</TypeName>
              <TypeName>app:place</TypeName>
            </DescribeFeatureType>""",
            id="xmlns-app",
        ),
        Post(
            # default namespace
            f"""
            <wfs:DescribeFeatureType version="2.0.0" service="WFS"
                 xmlns:wfs="{xmlns.wfs}" xmlns="http://example.org/gisserver">
              <wfs:TypeName>restaurant</wfs:TypeName>
              <wfs:TypeName>place</wfs:TypeName>
            </wfs:DescribeFeatureType>""",
            id="xmlns-default",
        ),
        Post(
            # default namespace
            f"""
            <wfs:DescribeFeatureType version="2.0.0" service="WFS"
                 xmlns:wfs="{xmlns.wfs}" xmlns:ns0="http://example.org/gisserver">
              <wfs:TypeName>ns0:restaurant</wfs:TypeName>
              <wfs:TypeName>ns0:place</wfs:TypeName>
            </wfs:DescribeFeatureType>""",
            id="xmlns-ns0",
        ),
    )
    def test_type_names(self, ows_request):
        """This also tests whether the XML namespace parsing works."""
        assert ows_request.typeNames == [
            "{http://example.org/gisserver}restaurant",
            "{http://example.org/gisserver}place",
        ]


class TestGetFeature:
    """Test GetFeature parsing."""

    @parametrize_ows_request(
        Get("?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=place"),
        Post(
            f"""
            <wfs:GetFeature service="WFS" version="2.0.0" {XML_NS_WFS}>
              <wfs:Query typeNames="app:place"></wfs:Query>
            </wfs:GetFeature>"""
        ),
    )
    def test_minimal(self, ows_request):
        """Prove that minimal KVP request is parsed."""
        assert ows_request == wfs20.GetFeature(
            service="WFS",
            version="2.0.0",
            handle=None,
            queries=[
                wfs20.AdhocQuery(
                    typeNames=[
                        "{http://example.org/gisserver}place",
                    ]
                )
            ],
            outputFormat="application/gml+xml; version=3.2",
            resultType=wfs20.ResultType.results,
        )

    @parametrize_ows_request(
        Get(
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById&ID=place.2"
        ),
        Post(
            f"""
            <wfs:GetFeature service="WFS" version="2.0.0" {XML_NS_WFS}>
              <wfs:StoredQuery id="urn:ogc:def:query:OGC-WFS::GetFeatureById">
                <wfs:Parameter name="id">restaurant.0</wfs:Parameter>
              </wfs:StoredQuery>
            </wfs:GetFeature>"""
        ),
    )
    def test_stored_query(self, ows_request):
        """Prove that stored queries are parsed."""
        ows_request = parse_get_request(
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById&ID=place.2",
            ns_aliases={"": "http://example.org/gisserver"},
        )
        assert ows_request == wfs20.GetFeature(
            service="WFS",
            version="2.0.0",
            handle=None,
            queries=[
                wfs20.StoredQuery(
                    id="urn:ogc:def:query:OGC-WFS::GetFeatureById",
                    parameters={"id": "place.2"},
                )
            ],
        )

    FILTER_MINIMAL = """
    <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
        <fes:PropertyIsEqualTo>
            <fes:ValueReference>app:SomeProperty</fes:ValueReference>
            <fes:Literal>100</fes:Literal>
        </fes:PropertyIsEqualTo>
    </fes:Filter>"""

    @parametrize_ows_request(
        Get(
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
            f"&TYPENAMES=app:place&FILTER={quote(FILTER_MINIMAL.strip())}"
        ),
        Post(
            f"""
            <wfs:GetFeature service="WFS" version="2.0.0" {XML_NS_WFS}>
              <wfs:Query typeNames="app:place">
                {FILTER_MINIMAL}
              </wfs:Query>
            </wfs:GetFeature>"""
        ),
    )
    def test_filter_minimal(self, ows_request):
        """Prove that stored queries are parsed."""
        assert ows_request == wfs20.GetFeature(
            service="WFS",
            version="2.0.0",
            handle=None,
            queries=[
                wfs20.AdhocQuery(
                    typeNames=[
                        "{http://example.org/gisserver}place",
                    ],
                    filter=fes20.Filter(
                        predicate=BinaryComparisonOperator(
                            operatorType=BinaryComparisonName.PropertyIsEqualTo,
                            expression=(
                                fes20.ValueReference("app:SomeProperty"),
                                Literal("100", raw_type=None),
                            ),
                        ),
                    ),
                    sortBy=None,
                )
            ],
        )

    @parametrize_ows_request(
        Get("?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&RESOURCEID=place.2"),
        Post(
            # In the post example, declare the namespace to have similar resolving.
            # Otherwise, the resolving happens by fix_type_name().
            f"""
            <wfs:GetFeature service="WFS" version="2.0.0" {XML_NS_WFS}>
              <wfs:Query typeNames="place">
                <fes:Filter>
                  <fes:ResourceId rid="place.2" xmlns="http://example.org/gisserver" />
                </fes:Filter>
              </wfs:Query>
            </wfs:GetFeature>"""
        ),
    )
    def test_resource_id(self, ows_request):
        """Prove that RESOURCEID KVP is parsed."""
        assert ows_request == wfs20.GetFeature(
            service="WFS",
            version="2.0.0",
            handle=None,
            queries=[
                wfs20.AdhocQuery(
                    typeNames=["place"] if ows_request.method == "POST" else [],
                    filter=fes20.Filter(
                        predicate=IdOperator(
                            [
                                fes20.ResourceId(
                                    rid="place.2", type_name="{http://example.org/gisserver}place"
                                ),
                            ],
                        )
                    ),
                )
            ],
        )


class TestGetPropertyValue:
    """Test GetPropertyValue parsing."""

    @parametrize_ows_request(
        Get(
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetPropertyValue&TYPENAMES=place"
            "&VALUEREFERENCE=app:name"
        ),
        Post(
            f"""
            <wfs:GetPropertyValue service="WFS" version="2.0.0" valueReference="app:name" {XML_NS_WFS}>
              <wfs:Query typeNames="app:place"></wfs:Query>
            </wfs:GetPropertyValue>"""
        ),
    )
    def test_minimal(self, ows_request):
        """Prove that minimal KVP request is parsed."""
        assert ows_request == wfs20.GetPropertyValue(
            service="WFS",
            version="2.0.0",
            handle=None,
            queries=[
                wfs20.AdhocQuery(
                    typeNames=[
                        "{http://example.org/gisserver}place",
                    ],
                )
            ],
            outputFormat="application/gml+xml; version=3.2",
            resultType=wfs20.ResultType.results,
            valueReference=fes20.ValueReference("app:name"),
        )
