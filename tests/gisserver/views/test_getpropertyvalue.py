import django
import pytest
from urllib.parse import quote_plus

from tests.constants import NAMESPACES
from tests.gisserver.views.input import (
    FILTERS,
    INVALID_FILTERS,
    POINT1_XML_WGS84,
    SORT_BY,
)
from tests.utils import WFS_20_XSD, assert_xml_equal, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


def read_response(response) -> str:
    # works for all HttpResponse subclasses.
    return b"".join(response).decode()


@pytest.mark.django_db
class TestGetPropertyValue:
    """All tests for the GetPropertyValue method."""

    def test_get(self, client, restaurant, bad_restaurant):
        """Prove that the happy flow works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&VALUEREFERENCE=name"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:ValueCollection
       xmlns:app="http://example.org/gisserver"
       xmlns:gml="http://www.opengis.net/gml/3.2"
       xmlns:wfs="http://www.opengis.net/wfs/2.0"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
       timeStamp="{timestamp}" numberMatched="2" numberReturned="2">
  <wfs:member>
    <app:name>Café Noir</app:name>
  </wfs:member>
  <wfs:member>
    <app:name>Foo Bar</app:name>
  </wfs:member>
</wfs:ValueCollection>""",  # noqa: E501
        )

    def test_get_location(self, client, restaurant):
        """Prove that rendering geometry values also works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&VALUEREFERENCE=location"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:ValueCollection
       xmlns:app="http://example.org/gisserver"
       xmlns:gml="http://www.opengis.net/gml/3.2"
       xmlns:wfs="http://www.opengis.net/wfs/2.0"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
       timeStamp="{timestamp}" numberMatched="1" numberReturned="1">
  <wfs:member>
    <app:location>
      <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
        <gml:pos>{POINT1_XML_WGS84}</gml:pos>
      </gml:Point>
    </app:location>
  </wfs:member>
</wfs:ValueCollection>""",  # noqa: E501
        )

    @pytest.mark.parametrize("filter_name", list(FILTERS.keys()))
    def test_get_filter(self, client, restaurant, bad_restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter = FILTERS[filter_name].strip()

        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&VALUEREFERENCE=name&FILTER=" + quote_plus(filter)
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # Assert that the correct object was matched
        name = xml_doc.find("wfs:member/app:name", namespaces=NAMESPACES).text
        assert name == "Café Noir"

    @pytest.mark.parametrize("filter_name", list(INVALID_FILTERS.keys()))
    def test_get_filter_invalid(self, client, restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter, expect_msg = INVALID_FILTERS[filter_name]

        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&VALUEREFERENCE=name&FILTER=" + quote_plus(filter.strip())
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "InvalidParameterValue"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == expect_msg

    def test_get_unauth(self, client):
        """Prove that features may block access.
        Note that HTTP 403 is not in the WFS 2.0 spec, but still useful to have.
        """
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=denied-feature"
            "&VALUEREFERENCE=name"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 403, content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "PermissionDenied"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == "No access to this feature."

    def test_pagination(self, client, restaurant, bad_restaurant):
        """Prove that that parsing BBOX=... works"""
        names = []
        url = (
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&VALUEREFERENCE=name&SORTBY=name"
        )
        for _ in range(4):  # test whether last page stops
            response = client.get(f"{url}&COUNT=1")
            content = read_response(response)
            assert response["content-type"] == "text/xml; charset=utf-8", content
            assert response.status_code == 200, content
            assert "</wfs:ValueCollection>" in content

            # Validate against the WFS 2.0 XSD
            xml_doc = validate_xsd(content, WFS_20_XSD)
            assert xml_doc.attrib["numberMatched"] == "2"
            assert xml_doc.attrib["numberReturned"] == "1"

            # Collect the names
            members = xml_doc.findall("wfs:member", namespaces=NAMESPACES)
            names.extend(
                res.find("app:name", namespaces=NAMESPACES).text for res in members
            )
            url = xml_doc.attrib.get("next")
            if not url:
                break

        # Prove that both items were returned
        assert len(names) == 2
        assert names[0] != names[1]

    @pytest.mark.parametrize("ordering", list(SORT_BY.keys()))
    def test_get_sort_by(self, client, restaurant, bad_restaurant, ordering):
        """Prove that that parsing BBOX=... works"""
        sort_by, expect = SORT_BY[ordering]
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            f"&VALUEREFERENCE=name&SORTBY={sort_by}"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"

        # Test sort ordering.
        members = xml_doc.findall("wfs:member", namespaces=NAMESPACES)
        names = [res.find("app:name", namespaces=NAMESPACES).text for res in members]
        assert names == expect

    def test_resource_id(self, client, restaurant, bad_restaurant):
        """Prove that fetching objects by ID works."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            f"&RESOURCEID=restaurant.{restaurant.id}&VALUEREFERENCE=name"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # Test sort ordering.
        members = xml_doc.findall("wfs:member", namespaces=NAMESPACES)
        names = [res.find("app:name", namespaces=NAMESPACES).text for res in members]
        assert names == ["Café Noir"]

    def test_resource_id_unknown_id(self, client, restaurant, bad_restaurant):
        """Prove that unknown IDs simply return an empty list."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            f"&RESOURCEID=restaurant.0&VALUEREFERENCE=name"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "0"
        assert xml_doc.attrib["numberReturned"] == "0"

        # Test sort ordering.
        members = xml_doc.findall("wfs:member", namespaces=NAMESPACES)
        assert len(members) == 0

    def test_resource_id_typename_mismatch(self, client, restaurant, bad_restaurant):
        """Prove that TYPENAMES should be omitted, or match the RESOURCEID."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            "&TYPENAMES=mini-restaurant"
            f"&RESOURCEID=restaurant.{restaurant.id}&VALUEREFERENCE=name"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content
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

    def test_resource_id_invalid(self, client, restaurant, bad_restaurant):
        """Prove that TYPENAMES should be omitted, or match the RESOURCEID."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            f"&RESOURCEID=restaurant.ABC&VALUEREFERENCE=name"
        )
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

    def test_get_feature_by_id_stored_query(self, client, restaurant, bad_restaurant):
        """Prove that fetching objects by ID works."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            f"&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            f"&ID=restaurant.{restaurant.id}&VALUEREFERENCE=name"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</app:restaurant>" not in content
        assert "</wfs:FeatureCollection>" not in content

        # See whether our feature is rendered
        # For GetFeatureById, no <wfs:FeatureCollection> is returned.
        assert_xml_equal(
            content,
            f"""<app:name xmlns:app="http://example.org/gisserver"
                          xmlns:gml="http://www.opengis.net/gml/3.2">Café Noir</app:name>""",
        )

    def test_get_feature_by_id_bad_id(self, client, restaurant, bad_restaurant):
        """Prove that invalid IDs are properly handled."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            f"&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            f"&ID=restaurant.ABC&VALUEREFERENCE=name"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "InvalidParameterValue"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        expect = (
            "Invalid ID value: Field 'id' expected a number but got 'ABC'."
            if django.VERSION >= (3, 0)
            else "Invalid ID value: invalid literal for int() with base 10: 'ABC'"
        )
        assert message == expect

    def test_get_feature_by_id_404(self, client, restaurant, bad_restaurant):
        """Prove that missing IDs are properly handled."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            f"&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            f"&ID=restaurant.0&VALUEREFERENCE=name"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 404, content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "NotFound"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == "Feature not found with ID 0."
