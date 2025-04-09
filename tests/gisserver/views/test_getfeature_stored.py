from xml.etree.ElementTree import QName

import pytest

from tests.requests import Get, Post, parametrize_response
from tests.utils import (
    NAMESPACES,
    WFS_20_XSD,
    XML_NS,
    assert_xml_equal,
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
            lambda id: "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            f"&ID=restaurant.{id}"
        ),
        Post(
            lambda id: f"""<GetFeature service="WFS" version="2.0.0"
				storedQueryId="urn:ogc:def:query:OGC-WFS::GetFeatureById" id="restaurant.{id}" {XML_NS}>
				</GetFeature>"""
        ),
    )
    def test_get_feature_by_id_stored_query(
        self, client, restaurant, bad_restaurant, coordinates, response
    ):
        """Prove that fetching objects by ID works."""
        res = response(restaurant.id)
        content = read_response(res)
        assert res["content-type"] == "text/xml; charset=utf-8", content
        assert res.status_code == 200, content
        assert "</app:restaurant>" in content
        assert "</wfs:FeatureCollection>" not in content

        # Fetch the XSD of the service itself.
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=restaurant"
        )
        xsd_content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, xsd_content=xsd_content)
        assert xml_doc.tag == QName(NAMESPACES["app"], "restaurant").text

        # See whether our feature is rendered
        # For GetFeatureById, no <wfs:FeatureCollection> is returned.
        assert_xml_equal(
            content,
            f"""<app:restaurant gml:id="restaurant.{restaurant.id}"
   xmlns:app="http://example.org/gisserver" xmlns:gml="http://www.opengis.net/gml/3.2">
    <gml:name>Café Noir</gml:name>
    <gml:boundedBy>
        <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{coordinates.point1_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point1_xml_wgs84}</gml:upperCorner>
        </gml:Envelope>
    </gml:boundedBy>
    <app:id>{restaurant.id}</app:id>
    <app:name>Café Noir</app:name>
    <app:city_id>{restaurant.city_id}</app:city_id>
    <app:location>
        <gml:Point gml:id="Restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{coordinates.point1_xml_wgs84}</gml:pos>
        </gml:Point>
    </app:location>
    <app:rating>5.0</app:rating>
    <app:is_open>true</app:is_open>
    <app:created>2020-04-05T12:11:10+00:00</app:created>
    <app:tags>cafe</app:tags>
    <app:tags>black</app:tags>
</app:restaurant>""",  # noqa: E501
        )

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            "&ID=restaurant.ABC"
        ),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0"
				storedQueryId="urn:ogc:def:query:OGC-WFS::GetFeatureById" id="restaurant.ABC" {XML_NS}>
				</GetFeature>"""
        ),
    )
    def test_get_feature_by_id_bad_id(self, client, restaurant, bad_restaurant, response):
        """Prove that invalid IDs are properly handled."""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "InvalidParameterValue"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == "Invalid ID value: Field 'id' expected a number but got 'ABC'."

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            "&ID=restaurant.0"
        ),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0"
				storedQueryId="urn:ogc:def:query:OGC-WFS::GetFeatureById" id="restaurant.0" {XML_NS}>
				</GetFeature>"""
        ),
    )
    def test_get_feature_by_id_404(self, restaurant, bad_restaurant, response):
        """Prove that missing IDs are properly handled."""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 404, content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "NotFound"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == "Feature not found with ID restaurant.0."
