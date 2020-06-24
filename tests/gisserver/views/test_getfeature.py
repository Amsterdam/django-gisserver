import json
from urllib.parse import quote_plus
from xml.etree.ElementTree import QName

import django
import pytest
from gisserver.types import WGS84
from tests.constants import NAMESPACES
from tests.gisserver.views.input import (
    FILTERS,
    INVALID_FILTERS,
    POINT1_EWKT,
    POINT1_GEOJSON,
    POINT1_XML_RD,
    POINT1_XML_WGS84,
    POINT2_EWKT,
    POINT2_GEOJSON,
    POINT2_XML_WGS84,
    SORT_BY,
)
from tests.test_gisserver.models import Restaurant
from tests.utils import WFS_20_XSD, assert_xml_equal, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


def read_response(response) -> str:
    # works for all HttpResponse subclasses.
    return b"".join(response).decode()


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @staticmethod
    def read_json(content) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            snippet = content[e.pos - 300 : e.pos + 300]
            snippet = snippet[snippet.index("\n") :]  # from last newline
            raise AssertionError(f"Parsing JSON failed: {e}\nNear: {snippet}") from None

    def test_get(self, client, restaurant):
        """Prove that the happy flow works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # See whether our feature is rendered
        feature = xml_doc.find("wfs:member/app:restaurant", namespaces=NAMESPACES)
        assert feature is not None
        assert feature.find("app:name", namespaces=NAMESPACES).text == restaurant.name
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   xmlns:wfs="http://www.opengis.net/wfs/2.0"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
   timeStamp="{timestamp}" numberMatched="1" numberReturned="1">

    <wfs:member>
      <app:restaurant gml:id="restaurant.{restaurant.id}">
        <gml:name>Café Noir</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{POINT1_XML_WGS84}</gml:lowerCorner>
            <gml:upperCorner>{POINT1_XML_WGS84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{restaurant.id}</app:id>
        <app:name>Café Noir</app:name>
        <app:city_id>{restaurant.city_id}</app:city_id>
        <app:location>
          <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{POINT1_XML_WGS84}</gml:pos>
          </gml:Point>
        </app:location>
        <app:rating>5.0</app:rating>
        <app:created>2020-04-05T12:11:10+00:00</app:created>
      </app:restaurant>
    </wfs:member>
</wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_get_empty_geometry(self, client):
        """Prove that the empty geometry values don't crash the rendering."""
        restaurant = Restaurant.objects.create(name="Empty")
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        feature = xml_doc.find("wfs:member/app:restaurant", namespaces=NAMESPACES)
        assert feature.find("app:location", namespaces=NAMESPACES).text is None
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection
       xmlns:app="http://example.org/gisserver"
       xmlns:gml="http://www.opengis.net/gml/3.2"
       xmlns:wfs="http://www.opengis.net/wfs/2.0"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
       timeStamp="{timestamp}" numberMatched="1" numberReturned="1">

        <wfs:member>
          <app:restaurant gml:id="restaurant.{restaurant.id}">
            <gml:name>Empty</gml:name>
            <app:id>{restaurant.id}</app:id>
            <app:name>Empty</app:name>
            <app:city_id xsi:nil="true" />
            <app:location xsi:nil="true" />
            <app:rating>0.0</app:rating>
            <app:created>2020-04-05T12:11:10+00:00</app:created>
          </app:restaurant>
        </wfs:member>
    </wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_get_limited_fields(self, client, restaurant):
        """Prove that the 'FeatureType(fields=..)' reduces the returned fields."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=mini-restaurant"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # See whether our feature is rendered
        feature = xml_doc.find("wfs:member/app:mini-restaurant", namespaces=NAMESPACES)
        assert feature is not None
        assert feature.find("gml:name", namespaces=NAMESPACES).text == restaurant.name
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   xmlns:wfs="http://www.opengis.net/wfs/2.0"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=mini-restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
   timeStamp="{timestamp}" numberMatched="1" numberReturned="1">

    <wfs:member>
      <app:mini-restaurant gml:id="mini-restaurant.{restaurant.id}">
        <gml:name>Café Noir</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{POINT1_XML_WGS84}</gml:lowerCorner>
            <gml:upperCorner>{POINT1_XML_WGS84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:location>
          <gml:Point gml:id="mini-restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{POINT1_XML_WGS84}</gml:pos>
          </gml:Point>
        </app:location>
      </app:mini-restaurant>
    </wfs:member>
</wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_get_complex(self, client, restaurant, bad_restaurant):
        """Prove that rendering complex types works."""
        response = client.get(
            "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&TYPENAMES=restaurant"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"

        # See whether our feature is rendered
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   xmlns:wfs="http://www.opengis.net/wfs/2.0"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs-complextypes/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
   timeStamp="{timestamp}" numberMatched="2" numberReturned="2">

    <wfs:member>
      <app:restaurant gml:id="restaurant.{restaurant.id}">
        <gml:name>Café Noir</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{POINT1_XML_WGS84}</gml:lowerCorner>
            <gml:upperCorner>{POINT1_XML_WGS84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{restaurant.id}</app:id>
        <app:name>Café Noir</app:name>
        <app:city>
          <app:id>{restaurant.city_id}</app:id>
          <app:name>CloudCity</app:name>
        </app:city>
        <app:location>
          <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{POINT1_XML_WGS84}</gml:pos>
          </gml:Point>
        </app:location>
        <app:rating>5.0</app:rating>
        <app:created>2020-04-05T12:11:10+00:00</app:created>
      </app:restaurant>
    </wfs:member>

    <wfs:member>
      <app:restaurant gml:id="restaurant.{bad_restaurant.id}">
        <gml:name>Foo Bar</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{POINT2_XML_WGS84}</gml:lowerCorner>
            <gml:upperCorner>{POINT2_XML_WGS84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{bad_restaurant.id}</app:id>
        <app:name>Foo Bar</app:name>
        <app:city xsi:nil="true" />
        <app:location>
          <gml:Point gml:id="restaurant.{bad_restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{POINT2_XML_WGS84}</gml:pos>
          </gml:Point>
        </app:location>
        <app:rating>1.0</app:rating>
        <app:created>2020-04-05T12:11:10+00:00</app:created>
      </app:restaurant>
    </wfs:member>

</wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_get_srs_name(self, client, restaurant):
        """Prove that specifying SRSNAME works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&SRSNAME=urn:ogc:def:crs:EPSG::28992"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # Prove that the output is now rendered in EPSG:28992
        feature = xml_doc.find("wfs:member/app:restaurant", namespaces=NAMESPACES)
        geometry = feature.find("app:location/gml:Point", namespaces=NAMESPACES)
        assert geometry.attrib["srsName"] == "urn:ogc:def:crs:EPSG::28992"

        timestamp = xml_doc.attrib["timeStamp"]
        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection
       xmlns:app="http://example.org/gisserver"
       xmlns:gml="http://www.opengis.net/gml/3.2"
       xmlns:wfs="http://www.opengis.net/wfs/2.0"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
       timeStamp="{timestamp}" numberMatched="1" numberReturned="1">

        <wfs:member>
          <app:restaurant gml:id="restaurant.{restaurant.id}">
            <gml:name>Café Noir</gml:name>
            <gml:boundedBy>
              <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::28992">
                <gml:lowerCorner>{POINT1_XML_RD}</gml:lowerCorner>
                <gml:upperCorner>{POINT1_XML_RD}</gml:upperCorner>
              </gml:Envelope>
            </gml:boundedBy>
            <app:id>{restaurant.id}</app:id>
            <app:name>Café Noir</app:name>
            <app:city_id>{restaurant.city_id}</app:city_id>
            <app:location>
              <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::28992">
                <gml:pos srsDimension="2">{POINT1_XML_RD}</gml:pos>
              </gml:Point>
            </app:location>
            <app:rating>5.0</app:rating>
            <app:created>2020-04-05T12:11:10+00:00</app:created>
          </app:restaurant>
        </wfs:member>
    </wfs:FeatureCollection>""",  # noqa: E501
        )

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
        assert name == "Café Noir"

    @pytest.mark.parametrize("filter_name", list(INVALID_FILTERS.keys()))
    def test_get_filter_invalid(self, client, restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter, expect_msg = INVALID_FILTERS[filter_name]

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
        assert exception.attrib["exceptionCode"] == "InvalidParameterValue"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == expect_msg

    def test_get_unauth(self, client):
        """Prove that features may block access.
        Note that HTTP 403 is not in the WFS 2.0 spec, but still useful to have.
        """
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=denied-feature"
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

    def test_get_hits(self, client, restaurant):
        """Prove that that parsing RESULTTYPE=hits works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&RESULTTYPE=hits"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "0"
        assert not xml_doc.getchildren()  # should not have children!
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   xmlns:wfs="http://www.opengis.net/wfs/2.0"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
   timeStamp="{timestamp}" numberMatched="1" numberReturned="0">
</wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_pagination(self, client, restaurant, bad_restaurant):
        """Prove that that parsing BBOX=... works"""
        names = []
        url = (
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&SORTBY=name"
        )
        for _ in range(4):  # test whether last page stops
            response = client.get(f"{url}&COUNT=1")
            content = read_response(response)
            assert response["content-type"] == "text/xml; charset=utf-8", content
            assert response.status_code == 200, content
            assert "</wfs:FeatureCollection>" in content

            # Validate against the WFS 2.0 XSD
            xml_doc = validate_xsd(content, WFS_20_XSD)
            assert xml_doc.attrib["numberMatched"] == "2"
            assert xml_doc.attrib["numberReturned"] == "1"

            # Collect the names
            restaurants = xml_doc.findall(
                "wfs:member/app:restaurant", namespaces=NAMESPACES
            )
            names.extend(
                res.find("app:name", namespaces=NAMESPACES).text for res in restaurants
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
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            f"&SORTBY={sort_by}"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"

        # Test sort ordering.
        restaurants = xml_doc.findall(
            "wfs:member/app:restaurant", namespaces=NAMESPACES
        )
        names = [
            res.find("app:name", namespaces=NAMESPACES).text for res in restaurants
        ]
        assert names == expect

    def test_get_geojson(
        self, client, restaurant, bad_restaurant, django_assert_max_num_queries
    ):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(2):
            response = client.get(
                "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                "&outputformat=geojson"
            )
            assert response["content-type"] == "application/json; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        data = self.read_json(content)

        assert data["features"][0]["geometry"]["coordinates"] == POINT1_GEOJSON
        assert data == {
            "type": "FeatureCollection",
            "links": [],
            "timeStamp": data["timeStamp"],
            "numberMatched": 2,
            "numberReturned": 2,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
            },
            "features": [
                {
                    "type": "Feature",
                    "id": f"restaurant.{restaurant.id}",
                    "geometry_name": "Café Noir",
                    "geometry": {"type": "Point", "coordinates": POINT1_GEOJSON},
                    "properties": {
                        "id": restaurant.id,
                        "name": "Café Noir",
                        "city_id": restaurant.city_id,
                        "rating": 5.0,
                        "created": "2020-04-05T12:11:10+00:00",
                    },
                },
                {
                    "type": "Feature",
                    "id": f"restaurant.{bad_restaurant.id}",
                    "geometry_name": "Foo Bar",
                    "geometry": {"type": "Point", "coordinates": POINT2_GEOJSON},
                    "properties": {
                        "id": bad_restaurant.id,
                        "name": "Foo Bar",
                        "city_id": None,
                        "rating": 1.0,
                        "created": "2020-04-05T12:11:10+00:00",
                    },
                },
            ],
        }

    def test_get_geojson_pagination(self, client):
        """Prove that the geojson export handles pagination."""
        # Create a large set so the buffer needs to flush.
        for i in range(1500):
            Restaurant.objects.create(name=f"obj#{i}")

        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&outputformat=geojson"
        )
        assert response["content-type"] == "application/json; charset=utf-8"
        content = read_response(response)

        # If the response is invalid json, there was likely
        # some exception that aborted further writing.
        data = self.read_json(content)

        assert len(data["features"]) == 1000
        assert data["numberReturned"] == 1000
        assert data["numberMatched"] == 1500

    def test_get_geojson_complex(
        self, client, restaurant, bad_restaurant, django_assert_max_num_queries
    ):
        """Prove that the geojson export works for complex field types.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(2):
            response = client.get(
                "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=geojson"
            )
            assert response["content-type"] == "application/json; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        data = self.read_json(content)

        assert data == {
            "type": "FeatureCollection",
            "links": [],
            "timeStamp": data["timeStamp"],
            "numberMatched": 2,
            "numberReturned": 2,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
            },
            "features": [
                {
                    "type": "Feature",
                    "id": f"restaurant.{restaurant.id}",
                    "geometry_name": "Café Noir",
                    "geometry": {"type": "Point", "coordinates": POINT1_GEOJSON},
                    "properties": {
                        "id": restaurant.id,
                        "name": "Café Noir",
                        "city": {
                            # City is expanded, following the type definition
                            "id": restaurant.city_id,
                            "name": "CloudCity",
                        },
                        "rating": 5.0,
                        "created": "2020-04-05T12:11:10+00:00",
                    },
                },
                {
                    "type": "Feature",
                    "id": f"restaurant.{bad_restaurant.id}",
                    "geometry_name": "Foo Bar",
                    "geometry": {"type": "Point", "coordinates": POINT2_GEOJSON},
                    "properties": {
                        "id": bad_restaurant.id,
                        "name": "Foo Bar",
                        "city": None,
                        "rating": 1.0,
                        "created": "2020-04-05T12:11:10+00:00",
                    },
                },
            ],
        }

    def test_get_csv(
        self, client, restaurant, bad_restaurant, django_assert_max_num_queries
    ):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(1):
            response = client.get(
                "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                "&outputformat=csv"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","city_id","location","rating","created"
"{restaurant.id}","Café Noir","{restaurant.city_id}","SRID=4326;{POINT1_EWKT}","5.0","2020-04-05 14:11:10"
"{bad_restaurant.id}","Foo Bar","","SRID=4326;{POINT2_EWKT}","1.0","2020-04-05 14:11:10"
""".lstrip()  # noqa: E501
        assert content == expect

    def test_resource_id(self, client, restaurant, bad_restaurant):
        """Prove that fetching objects by ID works."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&RESOURCEID=restaurant.{restaurant.id}&VALUEREFERENCE=name"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # Test sort ordering.
        restaurants = xml_doc.findall(
            "wfs:member/app:restaurant", namespaces=NAMESPACES
        )
        names = [
            res.find("app:name", namespaces=NAMESPACES).text for res in restaurants
        ]
        assert names == ["Café Noir"]

    def test_resource_id_unknown_id(self, client, restaurant, bad_restaurant):
        """Prove that unknown IDs simply return an empty list."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            f"&RESOURCEID=restaurant.0"
        )
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

    def test_resource_id_typename_mismatch(self, client, restaurant, bad_restaurant):
        """Prove that TYPENAMES should be omitted, or match the RESOURCEID."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&TYPENAMES=mini-restaurant"
            f"&RESOURCEID=restaurant.{restaurant.id}"
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
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&RESOURCEID=restaurant.ABC"
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
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            f"&ID=restaurant.{restaurant.id}"
        )
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
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
            <gml:lowerCorner>{POINT1_XML_WGS84}</gml:lowerCorner>
            <gml:upperCorner>{POINT1_XML_WGS84}</gml:upperCorner>
        </gml:Envelope>
    </gml:boundedBy>
    <app:id>{restaurant.id}</app:id>
    <app:name>Café Noir</app:name>
    <app:city_id>{restaurant.city_id}</app:city_id>
    <app:location>
        <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{POINT1_XML_WGS84}</gml:pos>
        </gml:Point>
    </app:location>
    <app:rating>5.0</app:rating>
    <app:created>2020-04-05T12:11:10+00:00</app:created>
</app:restaurant>""",  # noqa: E501
        )

    def test_get_feature_by_id_bad_id(self, client, restaurant, bad_restaurant):
        """Prove that invalid IDs are properly handled."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            f"&ID=restaurant.ABC"
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
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            f"&ID=restaurant.0"
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
