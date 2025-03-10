import re
from urllib.parse import quote_plus

import pytest

from gisserver.geometries import WGS84
from tests.constants import NAMESPACES, XML_NS
from tests.gisserver.views.input import (
    FILTERS,
    INVALID_FILTERS,
)
from tests.requests import Get, Post, parametrize_response
from tests.utils import WFS_20_XSD, read_response, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


def clean_filter_for_xml(xml):
    """Removes leading <? xml ?> tag"""
    return re.sub(r"<\?.*\?>", "", xml)


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @parametrize_response(
        [
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
        ]
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
        [
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
        ]
    )
    def test_get_bbox_no_result(self, restaurant, response):
        # Also prove that using a different BBOX gives empty results
        content = read_response(response)
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "0"
        assert xml_doc.attrib["numberReturned"] == "0"

    @parametrize_response(
        [
            Get(
                "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                "&FILTER=" + quote_plus(filter.strip()),
                id=name,
                url_type=type,
            )
            for (name, type, filter) in FILTERS
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
                url_type=type,
            )
            for (name, type, filter) in FILTERS
        ]
    )
    def test_get_filter(self, restaurant, restaurant_m2m, bad_restaurant, response):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        _assert_filter(response, expect_name="Café Noir")

    @parametrize_response(
        [
            Get(
                "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                "&FILTER=" + quote_plus(filter.strip()),
                expect=expect,
                id=name,
            )
            for name, (filter, expect, _) in INVALID_FILTERS.items()
        ]
        + [
            Post(
                f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
                <Query typeNames="restaurant">
                {clean_filter_for_xml(filter).strip()}
                </Query>
                </GetFeature>
                """,
                expect=expect,
                id=name,
            )
            for name, (filter, _, expect) in INVALID_FILTERS.items()
        ]
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

        assert exception.attrib["exceptionCode"] == response.expect.code, message
        assert message.startswith(response.expect.text)


def _assert_filter(response, expect_name):
    """Common part of filter logic"""
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

    # Assert that the correct object was matched
    name = feature.find("app:name", namespaces=NAMESPACES).text
    assert name == expect_name
