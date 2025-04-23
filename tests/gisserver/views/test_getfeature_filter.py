from urllib.parse import quote_plus

import django
import pytest

from gisserver.geometries import WGS84
from tests.gisserver.views.input import (
    FILTERS,
    GENERATED_FIELD_FILTER,
    INVALID_FILTERS,
)
from tests.requests import Get, Post, Url, parametrize_response
from tests.utils import (
    NAMESPACES,
    WFS_20_AND_GML_XSD,
    WFS_20_XSD,
    XML_NS,
    XML_NS_WFS,
    assert_xml_equal,
    clean_filter_for_xml,
    read_response,
    validate_xsd,
)

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&BBOX=122400,486200,122500,486300,urn:ogc:def:crs:EPSG::28992"
        ),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
            <Query typeNames="restaurant">
            <fes:Filter>
                <fes:BBOX>
                    <gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992">
                        <gml:lowerCorner>122400 486200</gml:lowerCorner>
                        <gml:upperCorner>122500 486300</gml:upperCorner>
                    </gml:Envelope>
                </fes:BBOX>
            </fes:Filter>
            </Query>
            </GetFeature>
            """
        ),
    )
    def test_get_bbox(self, restaurant, response):
        """Prove that that parsing BBOX=... works"""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # Prove that the output is still rendered in WGS84
        feature = xml_doc.find("wfs:member/app:restaurant", namespaces=NAMESPACES)
        geometry = feature.find("app:location/gml:Point", namespaces=NAMESPACES)
        assert geometry.attrib["srsName"] == WGS84.urn

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&BBOX=100,100,200,200,urn:ogc:def:crs:EPSG::28992"
        ),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
                <Query typeNames="restaurant">
                <fes:Filter>
                    <fes:BBOX>
                        <gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992">
                            <gml:lowerCorner>100 100</gml:lowerCorner>
                            <gml:upperCorner>200 200</gml:upperCorner>
                        </gml:Envelope>
                    </fes:BBOX>
                </fes:Filter>
                </Query>
                </GetFeature>
                """
        ),
    )
    def test_get_bbox_no_result(self, restaurant, response):
        # Also prove that using a different BBOX gives empty results
        content = read_response(response)
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "0"
        assert xml_doc.attrib["numberReturned"] == "0"

    @pytest.mark.skipif(
        django.VERSION < (5, 0), reason="GeneratedField is only available in Django >= 5"
    )
    def test_get_bbox_generated_field(self, client, generated_field):
        """Prove that that parsing BBOX=... works for GeneratedField"""
        # The `geometry` field falls outside of this bbox, only the
        # `geometry_translated` GeneratedField falls inside it.
        response = client.get(
            "/v1/wfs-gen-field/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=modelwithgeneratedfields"
            "&BBOX=5,53,6,55,urn:ogc:def:crs:EPSG::4326"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"
        # Prove that the output is still rendered in WGS84
        feature = xml_doc.find("wfs:member/app:modelwithgeneratedfields", namespaces=NAMESPACES)
        geometry = feature.find("app:geometry/gml:Point", namespaces=NAMESPACES)
        assert geometry.attrib["srsName"] == WGS84.urn

    @parametrize_response(
        *(
            [
                Get(
                    "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                    "&FILTER=" + quote_plus(filter.strip()),
                    id=name,
                    url=url,
                    expect=expect,
                )
                for (name, url, filter, *expect) in FILTERS
            ]
            + [
                Post(
                    f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
                <Query typeNames="restaurant">
                {clean_filter_for_xml(filter).strip()}
                </Query>
                </GetFeature>
                """,
                    id=name,
                    url=url,
                    expect=expect,
                )
                for (name, url, filter, *expect) in FILTERS
                if name != "fes1"
            ]
        )
    )
    def test_get_filter(self, restaurant, restaurant_m2m, bad_restaurant, response):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        _assert_filter(response, "Café Noir", *response.expect)

    @parametrize_response(
        *(
            [
                Get(
                    "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                    "&FILTER=" + quote_plus(filter.strip()),
                    expect=expect_get,
                    id=name,
                )
                for name, (filter, expect_get, _) in INVALID_FILTERS.items()
            ]
            + [
                Post(
                    f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
                <Query typeNames="restaurant">
                {clean_filter_for_xml(filter).strip()}
                </Query>
                </GetFeature>
                """,
                    expect=expect_post or expect_get,
                    id=name,
                    validate_xml=False,
                )
                for name, (filter, expect_get, expect_post) in INVALID_FILTERS.items()
            ]
        )
    )
    def test_get_filter_invalid(self, client, restaurant, response):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        message = exception.find("ows:ExceptionText", NAMESPACES).text
        expect_message = response.expect.text

        assert message.startswith(expect_message), f"got: {message}, expect: {expect_message}"
        assert exception.attrib["exceptionCode"] == response.expect.code, message

    def test_post_exception_handle(self, client):
        """Prove that the 'handle' is set."""
        xml = f"""
            <wfs:GetFeature service="WFS" version="2.0.0" {XML_NS_WFS} handle="foobar">
                <wfs:Query typeNames="restaurant">
                    <fes:Filter>
                        <fes:PropertyIsGreaterThanOrEqualTo>
                            <fes:ValueReference>created</fes:ValueReference>
                            <fes:Literal>abc</fes:Literal>
                        </fes:PropertyIsGreaterThanOrEqualTo>
                    </fes:Filter>
                </wfs:Query>
            </wfs:GetFeature>
        """
        validate_xsd(xml, WFS_20_AND_GML_XSD)
        response = client.post(Url.NORMAL, data=xml, content_type="application/xml")
        content = read_response(response)

        # Note locator == handle
        assert_xml_equal(
            content,
            """<ows:ExceptionReport version="2.0.0"
 xmlns:ows="http://www.opengis.net/ows/1.1"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xml:lang="en-US"
 xsi:schemaLocation="http://www.opengis.net/ows/1.1 http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd">
  <ows:Exception exceptionCode="OperationParsingFailed" locator="foobar">

    <ows:ExceptionText>Invalid data for the &#x27;created&#x27; property: Date must be in YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format.</ows:ExceptionText>

  </ows:Exception>
</ows:ExceptionReport>""",
        )

    @pytest.mark.skipif(
        django.VERSION < (5, 0), reason="GeneratedField is only available in Django >= 5"
    )
    def test_get_filter_generated_field(self, client, generated_field):
        """Filters on a GeneratedField value."""
        response = client.get(
            "/v1/wfs-gen-field/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=modelwithgeneratedfields"
            "&FILTER=" + quote_plus(GENERATED_FIELD_FILTER["name_reversed"])
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # Prove that the output is still rendered in WGS84
        feature = xml_doc.find("wfs:member/app:modelwithgeneratedfields", namespaces=NAMESPACES)
        geometry = feature.find("app:geometry/gml:Point", namespaces=NAMESPACES)
        assert geometry.attrib["srsName"] == WGS84.urn

        # Assert that the correct object was matched
        name = feature.find("app:name", namespaces=NAMESPACES).text
        assert name == generated_field.name


def _assert_filter(response, expect_name, expect_number_matched=1):
    """Common part of filter logic"""
    content = read_response(response)
    assert response["content-type"] == "text/xml; charset=utf-8", content
    assert response.status_code == 200, content
    assert "</wfs:FeatureCollection>" in content

    # Validate against the WFS 2.0 XSD
    xml_doc = validate_xsd(content, WFS_20_XSD)
    assert xml_doc.attrib["numberMatched"] == str(expect_number_matched)
    assert xml_doc.attrib["numberReturned"] == str(expect_number_matched)

    # Prove that the output is still rendered in WGS84
    feature = xml_doc.find("wfs:member/app:restaurant", namespaces=NAMESPACES)
    geometry = feature.find("app:location/gml:Point", namespaces=NAMESPACES)
    assert geometry.attrib["srsName"] == WGS84.urn

    # Assert that the correct object was matched
    name = feature.find("app:name", namespaces=NAMESPACES).text
    assert name == expect_name
