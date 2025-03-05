import re
from urllib.parse import quote_plus

import pytest

from gisserver.geometries import WGS84
from tests.constants import NAMESPACES, XML_NS
from tests.gisserver.views.input import (
    COMPLEX_FILTERS,
    FILTERS,
    FLATTENED_FILTERS,
    INVALID_FILTERS,
)
from tests.utils import WFS_20_XSD, read_response, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    def test_get_bbox(self, client, restaurant):
        """Prove that that parsing BBOX=... works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&BBOX=122400,486200,122500,486300,urn:ogc:def:crs:EPSG::28992"
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
        feature = xml_doc.find("wfs:member/app:restaurant", namespaces=NAMESPACES)
        geometry = feature.find("app:location/gml:Point", namespaces=NAMESPACES)
        assert geometry.attrib["srsName"] == WGS84.urn

        # Also prove that using a different BBOX gives empty results
        response2 = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&BBOX=100,100,200,200,urn:ogc:def:crs:EPSG::28992"
        )
        content2 = read_response(response2)
        xml_doc = validate_xsd(content2, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "0"
        assert xml_doc.attrib["numberReturned"] == "0"

    @pytest.mark.parametrize("filter_name", list(FILTERS.keys()))
    def test_get_filter(self, client, restaurant, bad_restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter = FILTERS[filter_name].strip()
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&FILTER=" + quote_plus(filter)
        )
        _assert_filter(response, expect_name="Café Noir")

    @pytest.mark.parametrize("filter_name", list(COMPLEX_FILTERS.keys()))
    def test_get_filter_complex(self, client, restaurant_m2m, bad_restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter = COMPLEX_FILTERS[filter_name].strip()
        response = client.get(
            "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&TYPENAMES=restaurant&FILTER=" + quote_plus(filter)
        )
        _assert_filter(response, expect_name="Café Noir")

    @pytest.mark.parametrize("filter_name", list(FLATTENED_FILTERS.keys()))
    def test_get_filter_flattened(self, client, restaurant, bad_restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... also works
        when the fields are flattened (model_attribute dot-notation).
        """
        filter = clean_filter_for_xml(FLATTENED_FILTERS[filter_name]).strip()
        xml = f"""<GetFeature xmlns="http://www.opengis.net/wfs/2.0" xmlns:fes="http://www.opengis.net/fes/2.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" service="WFS" version="2.0.0" xsi:schemaLocation="http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd">
            <Query typeNames="restaurant">
            {filter}
            </Query>
            </GetFeature>
            """
        response = client.post("/v1/wfs-flattened/", data=xml, content_type="application/xml")
        _assert_filter(response, expect_name="Café Noir")

    @pytest.mark.parametrize("filter_name", list(INVALID_FILTERS.keys()))
    def test_get_filter_invalid(self, client, restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter, expect_exception, _ = INVALID_FILTERS[filter_name]

        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&FILTER=" + quote_plus(filter.strip())
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        message = exception.find("ows:ExceptionText", NAMESPACES).text

        assert exception.attrib["exceptionCode"] == expect_exception.code, message
        assert message == expect_exception.text


@pytest.mark.django_db
class TestGetFeatureWithPostRequest:
    """All tests for the GetFeature method with a POST request.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    def test_post_bbox(self, client, restaurant):
        """Prove that that parsing BBOX=... works

        Note that we have to pass in the xmlns:gml namespace in order to parse the Envelope correctly
        """
        xml = f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
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
        response = client.post("/v1/wfs/", data=xml, content_type="application/xml")
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

        xml2 = f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
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
        # Also prove that using a different BBOX gives empty results
        response2 = client.post("/v1/wfs/", data=xml2, content_type="application/xml")
        content2 = read_response(response2)
        xml_doc = validate_xsd(content2, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "0"
        assert xml_doc.attrib["numberReturned"] == "0"

    @pytest.mark.parametrize("filter_name", list(FILTERS.keys()))
    def test_post_filter(self, client, restaurant, bad_restaurant, filter_name):
        filter = clean_filter_for_xml(FILTERS[filter_name]).strip()
        xml = f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
            <Query typeNames="restaurant">
            {filter}
            </Query>
            </GetFeature>
            """
        response = client.post("/v1/wfs/", data=xml, content_type="application/xml")
        _assert_filter(response, expect_name="Café Noir")

    @pytest.mark.parametrize("filter_name", list(COMPLEX_FILTERS.keys()))
    def test_post_filter_complex(self, client, restaurant_m2m, bad_restaurant, filter_name):
        """Prove that that parsing <fes:Filter>... works on post requests."""
        filter = clean_filter_for_xml(COMPLEX_FILTERS[filter_name]).strip()
        xml = f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
            <Query typeNames="restaurant">
            {filter}
            </Query>
            </GetFeature>
            """
        response = client.post("/v1/wfs-complextypes/", data=xml, content_type="application/xml")
        _assert_filter(response, expect_name="Café Noir")

    @pytest.mark.parametrize("filter_name", list(FLATTENED_FILTERS.keys()))
    def test_post_filter_flattened(self, client, restaurant, bad_restaurant, filter_name):
        """Prove that that parsing <fes:Filter>... also works
        when the fields are flattened (model_attribute dot-notation).
        """
        filter = clean_filter_for_xml(FLATTENED_FILTERS[filter_name]).strip()
        xml = f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
            <Query typeNames="restaurant">
            {filter}
            </Query>
            </GetFeature>
            """
        response = client.post("/v1/wfs-flattened/", data=xml, content_type="application/xml")
        _assert_filter(response, expect_name="Café Noir")


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


def clean_filter_for_xml(xml):
    """Removes leading <? xml ?> tag"""
    return re.sub(r"<\?.*\?>", "", xml)
