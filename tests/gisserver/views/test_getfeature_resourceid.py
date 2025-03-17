import pytest

from tests.requests import Get, Post, parametrize_response
from tests.utils import NAMESPACES, WFS_20_XSD, XML_NS, read_response, validate_xsd

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
            f"&RESOURCEID=restaurant.{id}"
        ),
        Post(
            lambda id: f"""<GetFeature service="WFS" version="2.0.0"
				resourceId="restaurant.{id}" {XML_NS}>
				</GetFeature>"""
        ),
    )
    def test_resource_id(self, restaurant, bad_restaurant, response):
        """Prove that fetching objects by ID works."""
        res = response(restaurant.id)
        content = read_response(res)
        assert res["content-type"] == "text/xml; charset=utf-8", content
        assert res.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # Test sort ordering.
        restaurants = xml_doc.findall("wfs:member/app:restaurant", namespaces=NAMESPACES)
        names = [res.find("app:name", namespaces=NAMESPACES).text for res in restaurants]
        assert names == ["Café Noir"]

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&RESOURCEID=restaurant.0"),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0"
				resourceId="restaurant.0" {XML_NS}>
				</GetFeature>"""
        ),
    )
    def test_resource_id_unknown_id(self, restaurant, bad_restaurant, response):
        """Prove that unknown IDs simply return an empty list."""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "0"
        assert xml_doc.attrib["numberReturned"] == "0"

        # Test sort ordering.
        members = xml_doc.findall("wfs:member", namespaces=NAMESPACES)
        assert len(members) == 0

    @parametrize_response(
        Get(
            lambda id: "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=mini-restaurant"
            f"&RESOURCEID=restaurant.{id}"
        ),
        Post(
            lambda id: f"""<GetFeature service="WFS" version="2.0.0"
				resourceId="restaurant.{id}" {XML_NS}>
                <Query typeNames="mini-restaurant"></Query>
				</GetFeature>"""
        ),
    )
    def test_resource_id_typename_mismatch(self, restaurant, bad_restaurant, response):
        """Prove that TYPENAMES should be omitted, or match the RESOURCEID."""
        res = response(restaurant.id)
        content = read_response(res)
        assert res["content-type"] == "text/xml; charset=utf-8", content
        assert res.status_code == 400, content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "InvalidParameterValue"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == (
            "When TYPENAMES and RESOURCEID are combined, "
            "the RESOURCEID type should be included in TYPENAMES."
        )

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&RESOURCEID=restaurant.ABC"),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0"
				resourceId="restaurant.ABC" {XML_NS}>
				</GetFeature>"""
        ),
    )
    def test_resource_id_invalid(self, restaurant, bad_restaurant, response):
        """Prove that TYPENAMES should be omitted, or match the RESOURCEID."""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert exception.attrib["exceptionCode"] == "InvalidParameterValue", message
        assert exception.attrib["locator"] == "resourceId", message
        # message differs in Django versions

    @parametrize_response(
        Get(
            lambda id1, id2: "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&RESOURCEID=restaurant.{id1},restaurant.{id2}"
        ),
        Post(
            lambda id1, id2: f"""<GetFeature service="WFS" version="2.0.0"
				resourceId="restaurant.{id1},restaurant.{id2}" {XML_NS}>
				</GetFeature>"""
        ),
    )
    def test_resource_id_multiple(self, client, restaurant, bad_restaurant, response):
        """Prove that fetching multiple IDs works."""
        res = response(restaurant.id, bad_restaurant.id)
        content = read_response(res)
        assert res["content-type"] == "text/xml; charset=utf-8", content
        assert res.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"

        # Test sort ordering.
        restaurants = xml_doc.findall("wfs:member/app:restaurant", namespaces=NAMESPACES)
        names = [res.find("app:name", namespaces=NAMESPACES).text for res in restaurants]
        assert names == ["Café Noir", "Foo Bar"]
