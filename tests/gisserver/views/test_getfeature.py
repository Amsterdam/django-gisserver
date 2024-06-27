from urllib.parse import quote_plus
from xml.etree.ElementTree import QName

import django
import orjson
import pytest

from gisserver import conf
from gisserver.geometries import WGS84
from tests.constants import NAMESPACES
from tests.gisserver.views.input import (
    COMPLEX_FILTERS,
    FILTERS,
    FLATTENED_FILTERS,
    INVALID_FILTERS,
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
            return orjson.loads(content)
        except orjson.JSONDecodeError as e:
            snippet = content[e.pos - 300 : e.pos + 300]
            snippet = snippet[snippet.index("\n") :]  # from last newline
            raise AssertionError(f"Parsing JSON failed: {e}\nNear: {snippet}") from None

    def test_get(self, client, restaurant, coordinates):
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
            <gml:lowerCorner>{coordinates.point1_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point1_xml_wgs84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{restaurant.id}</app:id>
        <app:name>Café Noir</app:name>
        <app:city_id>{restaurant.city_id}</app:city_id>
        <app:location>
          <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{coordinates.point1_xml_wgs84}</gml:pos>
          </gml:Point>
        </app:location>
        <app:rating>5.0</app:rating>
        <app:is_open>true</app:is_open>
        <app:created>2020-04-05T12:11:10+00:00</app:created>
        <app:tags>cafe</app:tags>
        <app:tags>black</app:tags>
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
        location = feature.find("app:location", namespaces=NAMESPACES)
        assert location is not None, content
        assert location.text is None
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
            <app:is_open>false</app:is_open>
            <app:created>2020-04-05T12:11:10+00:00</app:created>
          </app:restaurant>
        </wfs:member>
    </wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_get_limited_fields(self, client, restaurant, coordinates):
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
            <gml:lowerCorner>{coordinates.point1_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point1_xml_wgs84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:location>
          <gml:Point gml:id="mini-restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{coordinates.point1_xml_wgs84}</gml:pos>
          </gml:Point>
        </app:location>
      </app:mini-restaurant>
    </wfs:member>
</wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_get_complex(self, client, restaurant_m2m, bad_restaurant, coordinates):
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
      <app:restaurant gml:id="restaurant.{restaurant_m2m.id}">
        <gml:name>Café Noir</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{coordinates.point1_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point1_xml_wgs84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{restaurant_m2m.id}</app:id>
        <app:name>Café Noir</app:name>
        <app:city>
          <app:id>{restaurant_m2m.city_id}</app:id>
          <app:name>CloudCity</app:name>
        </app:city>
        <app:location>
          <gml:Point gml:id="restaurant.{restaurant_m2m.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{coordinates.point1_xml_wgs84}</gml:pos>
          </gml:Point>
        </app:location>
        <app:rating>5.0</app:rating>
        <app:is_open>true</app:is_open>
        <app:created>2020-04-05T12:11:10+00:00</app:created>
        <app:opening_hours>
          <app:weekday>4</app:weekday>
          <app:start_time>16:00:00</app:start_time>
          <app:end_time>23:30:00</app:end_time>
        </app:opening_hours>
        <app:opening_hours>
          <app:weekday>5</app:weekday>
          <app:start_time>16:00:00</app:start_time>
          <app:end_time>23:30:00</app:end_time>
        </app:opening_hours>
        <app:opening_hours>
          <app:weekday>6</app:weekday>
          <app:start_time>20:00:00</app:start_time>
          <app:end_time>23:30:00</app:end_time>
        </app:opening_hours>
        <app:tags>cafe</app:tags>
        <app:tags>black</app:tags>
      </app:restaurant>
    </wfs:member>

    <wfs:member>
      <app:restaurant gml:id="restaurant.{bad_restaurant.id}">
        <gml:name>Foo Bar</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{coordinates.point2_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point2_xml_wgs84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{bad_restaurant.id}</app:id>
        <app:name>Foo Bar</app:name>
        <app:city xsi:nil="true" />
        <app:location>
          <gml:Point gml:id="restaurant.{bad_restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{coordinates.point2_xml_wgs84}</gml:pos>
          </gml:Point>
        </app:location>
        <app:rating>1.0</app:rating>
        <app:is_open>false</app:is_open>
        <app:created>2020-04-05T20:11:10+00:00</app:created>
      </app:restaurant>
    </wfs:member>

</wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_get_flattened(self, client, restaurant, bad_restaurant, coordinates):
        """Prove that rendering complex types works."""
        response = client.get(
            "/v1/wfs-flattened/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
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
   xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs-flattened/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
   timeStamp="{timestamp}" numberMatched="2" numberReturned="2">

    <wfs:member>
      <app:restaurant gml:id="restaurant.{restaurant.id}">
        <gml:name>Café Noir</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{coordinates.point1_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point1_xml_wgs84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{restaurant.id}</app:id>
        <app:name>Café Noir</app:name>
        <app:city-id>{restaurant.city_id}</app:city-id>
        <app:city-name>CloudCity</app:city-name>
        <app:location>
          <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{coordinates.point1_xml_wgs84}</gml:pos>
          </gml:Point>
        </app:location>
        <app:rating>5.0</app:rating>
        <app:is_open>true</app:is_open>
        <app:created>2020-04-05T12:11:10+00:00</app:created>
        <app:tags>cafe</app:tags>
        <app:tags>black</app:tags>
      </app:restaurant>
    </wfs:member>

    <wfs:member>
      <app:restaurant gml:id="restaurant.{bad_restaurant.id}">
        <gml:name>Foo Bar</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{coordinates.point2_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point2_xml_wgs84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{bad_restaurant.id}</app:id>
        <app:name>Foo Bar</app:name>
        <app:city-id xsi:nil="true" />
        <app:city-name xsi:nil="true" />
        <app:location>
          <gml:Point gml:id="restaurant.{bad_restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{coordinates.point2_xml_wgs84}</gml:pos>
          </gml:Point>
        </app:location>
        <app:rating>1.0</app:rating>
        <app:is_open>false</app:is_open>
        <app:created>2020-04-05T20:11:10+00:00</app:created>
      </app:restaurant>
    </wfs:member>

</wfs:FeatureCollection>
""",  # noqa: E501
        )

    def test_get_srs_name(self, client, restaurant, coordinates):
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
                <gml:lowerCorner>{coordinates.point1_xml_rd}</gml:lowerCorner>
                <gml:upperCorner>{coordinates.point1_xml_rd}</gml:upperCorner>
              </gml:Envelope>
            </gml:boundedBy>
            <app:id>{restaurant.id}</app:id>
            <app:name>Café Noir</app:name>
            <app:city_id>{restaurant.city_id}</app:city_id>
            <app:location>
              <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::28992">
                <gml:pos srsDimension="2">{coordinates.point1_xml_rd}</gml:pos>
              </gml:Point>
            </app:location>
            <app:rating>5.0</app:rating>
            <app:is_open>true</app:is_open>
            <app:created>2020-04-05T12:11:10+00:00</app:created>
            <app:tags>cafe</app:tags>
            <app:tags>black</app:tags>
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
        self._assert_filter(response, expect_name="Café Noir")

    def _assert_filter(self, response, expect_name):
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

    @pytest.mark.parametrize("filter_name", list(COMPLEX_FILTERS.keys()))
    def test_get_filter_complex(self, client, restaurant_m2m, bad_restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter = COMPLEX_FILTERS[filter_name].strip()
        response = client.get(
            "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&TYPENAMES=restaurant&FILTER=" + quote_plus(filter)
        )
        self._assert_filter(response, expect_name="Café Noir")

    @pytest.mark.parametrize("filter_name", list(FLATTENED_FILTERS.keys()))
    def test_get_filter_flattened(self, client, restaurant, bad_restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... also works
        when the fields are flattened (model_attribute dot-notation).
        """
        filter = FLATTENED_FILTERS[filter_name].strip()
        response = client.get(
            "/v1/wfs-flattened/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&TYPENAMES=restaurant&FILTER=" + quote_plus(filter)
        )
        self._assert_filter(response, expect_name="Café Noir")

    @pytest.mark.parametrize("filter_name", list(INVALID_FILTERS.keys()))
    def test_get_filter_invalid(self, client, restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter, expect_exception = INVALID_FILTERS[filter_name]

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

    @pytest.mark.parametrize("use_count", [1, 0])
    def test_get_hits(self, client, restaurant, use_count, monkeypatch):
        """Prove that that parsing RESULTTYPE=hits works"""
        monkeypatch.setattr(conf, "GISSERVER_COUNT_NUMBER_MATCHED", use_count)
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

    @pytest.mark.parametrize("use_count", [1, 0])
    def test_pagination(
        self,
        client,
        restaurant,
        bad_restaurant,
        use_count,
        monkeypatch,
        django_assert_max_num_queries,
    ):
        """Prove that that pagination works.

        Two variations are tested; when normal COUNT happens,
        or a sentinel object is used to detect there are more results.
        """
        monkeypatch.setattr(conf, "GISSERVER_COUNT_NUMBER_MATCHED", use_count)
        names = []
        url = (
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&SORTBY=name&vendor-arg=foobar"
        )
        for _ in range(4):  # test whether last page stops
            with django_assert_max_num_queries(1 + use_count):
                response = client.get(f"{url}&COUNT=1")
                content = read_response(response)
            assert response["content-type"] == "text/xml; charset=utf-8", content
            assert response.status_code == 200, content
            assert "</wfs:FeatureCollection>" in content

            # Validate against the WFS 2.0 XSD
            xml_doc = validate_xsd(content, WFS_20_XSD)
            assert xml_doc.attrib["numberMatched"] == ("2" if use_count else "unknown")
            assert xml_doc.attrib["numberReturned"] == "1"

            # Collect the names
            restaurants = xml_doc.findall("wfs:member/app:restaurant", namespaces=NAMESPACES)
            names.extend(res.find("app:name", namespaces=NAMESPACES).text for res in restaurants)

            # Test pagination links
            next_url = xml_doc.attrib.get("next")
            if not next_url:
                assert xml_doc.attrib.get("previous") == (
                    "http://testserver/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                    "&TYPENAMES=restaurant&SORTBY=name"
                    "&vendor-arg=foobar"
                    "&COUNT=1&STARTINDEX=0"
                )
                break  # last page reached

            assert next_url == (
                "http://testserver/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&SORTBY=name"
                "&vendor-arg=foobar"
                "&COUNT=1&STARTINDEX=1"
            )

            # Resolve next page!
            url = next_url

        # Prove that both items were returned
        assert len(names) == 2
        assert names[0] != names[1]

    @pytest.mark.parametrize("ordering", list(SORT_BY.keys()))
    def test_get_sort_by(self, client, restaurant, bad_restaurant, ordering):
        """Prove that that sorting with SORTBY=... works"""
        sort_by, expect = SORT_BY[ordering]
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            f"&SORTBY={sort_by}"
        )
        self._assert_sort(response, expect)

    def _assert_sort(self, response, expect):
        """Common logic for sort tests"""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"

        # Test sort ordering.
        restaurants = xml_doc.findall("wfs:member/app:restaurant", namespaces=NAMESPACES)
        names = [res.find("app:name", namespaces=NAMESPACES).text for res in restaurants]
        assert names == expect

    SORT_BY_COMPLEX = {
        "city/name": ("city/name", ["Café Noir", "Foo Bar"]),
        "city/name-desc": ("city/name DESC", ["Foo Bar", "Café Noir"]),
    }

    @pytest.mark.parametrize("ordering", list(SORT_BY_COMPLEX.keys()))
    def test_get_sort_by_complex(self, client, restaurant, bad_restaurant, ordering):
        """Prove that sorting on XPath works for complex types"""
        sort_by, expect = self.SORT_BY_COMPLEX[ordering]
        response = client.get(
            "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&TYPENAMES=restaurant&SORTBY={sort_by}"
        )
        self._assert_sort(response, expect)

    SORT_BY_FLATTENED = {
        "city-name": ("city-name", ["Café Noir", "Foo Bar"]),
        "city-name-desc": ("city-name DESC", ["Foo Bar", "Café Noir"]),
    }

    @pytest.mark.parametrize("ordering", list(SORT_BY_FLATTENED.keys()))
    def test_get_sort_by_flattened(self, client, restaurant, bad_restaurant, ordering):
        """Prove that sorting on XPath works for flattened types"""
        sort_by, expect = self.SORT_BY_FLATTENED[ordering]
        response = client.get(
            "/v1/wfs-flattened/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&TYPENAMES=restaurant&SORTBY={sort_by}"
        )
        self._assert_sort(response, expect)

    def test_get_geojson(
        self,
        client,
        restaurant,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
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
            assert response["content-type"] == "application/geo+json; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        data = self.read_json(content)

        assert data["features"][0]["geometry"]["coordinates"] == coordinates.point1_geojson
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
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point1_geojson,
                    },
                    "properties": {
                        "id": restaurant.id,
                        "name": "Café Noir",
                        "city_id": restaurant.city_id,
                        "rating": 5.0,
                        "is_open": True,
                        "created": "2020-04-05T12:11:10+00:00",
                        "tags": ["cafe", "black"],
                    },
                },
                {
                    "type": "Feature",
                    "id": f"restaurant.{bad_restaurant.id}",
                    "geometry_name": "Foo Bar",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point2_geojson,
                    },
                    "properties": {
                        "id": bad_restaurant.id,
                        "name": "Foo Bar",
                        "city_id": None,
                        "rating": 1.0,
                        "is_open": False,
                        "created": "2020-04-05T20:11:10+00:00",
                        "tags": None,
                    },
                },
            ],
        }

    @pytest.mark.parametrize("use_count", [1, 0])
    def test_get_geojson_pagination(
        self, client, use_count, monkeypatch, django_assert_max_num_queries
    ):
        """Prove that the geojson export handles pagination.

        Two variations are tested; when normal COUNT happens,
        or a sentinel object is used to detect there are more results.
        """
        monkeypatch.setattr(conf, "GISSERVER_COUNT_NUMBER_MATCHED", use_count)

        # Create a large set so the buffer needs to flush.
        for i in range(1500):
            Restaurant.objects.create(name=f"obj#{i}")

        with django_assert_max_num_queries(1 + use_count):
            response = client.get(
                "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                "&vendor-arg=foobar&outputformat=geojson&COUNT=1000"
            )
            assert (
                response["content-type"] == "application/geo+json; charset=utf-8"
            )  # before stream starts
            content = read_response(response)

        # If the response is invalid json, there was likely
        # some exception that aborted further writing.
        data = self.read_json(content)

        assert len(data["features"]) == 1000
        assert data["numberReturned"] == 1000
        assert data["numberMatched"] == (1500 if use_count else None)

        # Check that the generates links are as expected, and don't mangle casing
        # as some project/vendor specific parameters might be case sensitive.
        assert data["links"] == [
            {
                "href": (
                    "http://testserver/v1/wfs/"
                    "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                    "&vendor-arg=foobar"
                    "&outputformat=geojson&COUNT=1000&STARTINDEX=1000"
                ),
                "rel": "next",
                "type": "application/geo+json",
                "title": "next page",
            }
        ]

    def test_get_geojson_complex(
        self,
        client,
        restaurant_m2m,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works for complex field types.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(3):
            response = client.get(
                "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=geojson"
            )
            assert response["content-type"] == "application/geo+json; charset=utf-8"
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
                    "id": f"restaurant.{restaurant_m2m.id}",
                    "geometry_name": "Café Noir",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point1_geojson,
                    },
                    "properties": {
                        "id": restaurant_m2m.id,
                        "name": "Café Noir",
                        "city": {
                            # City is expanded, following the type definition
                            "id": restaurant_m2m.city_id,
                            "name": "CloudCity",
                        },
                        "rating": 5.0,
                        "is_open": True,
                        "created": "2020-04-05T12:11:10+00:00",
                        "opening_hours": [
                            {
                                "weekday": 4,
                                "start_time": "16:00:00",
                                "end_time": "23:30:00",
                            },
                            {
                                "weekday": 5,
                                "start_time": "16:00:00",
                                "end_time": "23:30:00",
                            },
                            {
                                "weekday": 6,
                                "start_time": "20:00:00",
                                "end_time": "23:30:00",
                            },
                        ],
                        "tags": ["cafe", "black"],
                    },
                },
                {
                    "type": "Feature",
                    "id": f"restaurant.{bad_restaurant.id}",
                    "geometry_name": "Foo Bar",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point2_geojson,
                    },
                    "properties": {
                        "id": bad_restaurant.id,
                        "name": "Foo Bar",
                        "city": None,
                        "rating": 1.0,
                        "is_open": False,
                        "created": "2020-04-05T20:11:10+00:00",
                        "opening_hours": [],
                        "tags": None,
                    },
                },
            ],
        }

    def test_get_geojson_flattened(
        self,
        client,
        restaurant,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works for flattened field types."""
        with django_assert_max_num_queries(2):
            response = client.get(
                "/v1/wfs-flattened/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=geojson"
            )
            assert response["content-type"] == "application/geo+json; charset=utf-8"
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
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point1_geojson,
                    },
                    "properties": {
                        "id": restaurant.id,
                        "name": "Café Noir",
                        # City is flattened, following the type definition
                        "city-id": restaurant.city_id,
                        "city-name": "CloudCity",
                        "rating": 5.0,
                        "is_open": True,
                        "created": "2020-04-05T12:11:10+00:00",
                        "tags": ["cafe", "black"],
                    },
                },
                {
                    "type": "Feature",
                    "id": f"restaurant.{bad_restaurant.id}",
                    "geometry_name": "Foo Bar",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point2_geojson,
                    },
                    "properties": {
                        "id": bad_restaurant.id,
                        "name": "Foo Bar",
                        "city-id": None,
                        "city-name": None,
                        "rating": 1.0,
                        "is_open": False,
                        "created": "2020-04-05T20:11:10+00:00",
                        "tags": None,
                    },
                },
            ],
        }

    def test_get_csv(
        self,
        client,
        restaurant,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(3):
            response = client.get(
                "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                "&outputformat=csv"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","city_id","location","rating","is_open","created"
"{restaurant.id}","Café Noir","{restaurant.city_id}","{coordinates.point1_ewkt}","5.0","True","2020-04-05 12:11:10+00:00"
"{bad_restaurant.id}","Foo Bar","","{coordinates.point2_ewkt}","1.0","False","2020-04-05 20:11:10+00:00"
""".lstrip()  # noqa: E501
        assert content == expect

    def test_get_csv_complex(
        self,
        client,
        restaurant_m2m,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works, for complex results."""
        with django_assert_max_num_queries(1):
            response = client.get(
                "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=csv"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","city.id","city.name","location","rating","is_open","created"
"{restaurant_m2m.id}","Café Noir","{restaurant_m2m.city_id}","CloudCity","{coordinates.point1_ewkt}","5.0","True","2020-04-05 12:11:10+00:00"
"{bad_restaurant.id}","Foo Bar","","","{coordinates.point2_ewkt}","1.0","False","2020-04-05 20:11:10+00:00"
""".lstrip()  # noqa: E501
        assert content == expect
        assert "SRID=4326;" in content

    def test_get_csv_flattened(
        self,
        client,
        restaurant,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works, for flattened results."""
        with django_assert_max_num_queries(1):
            response = client.get(
                "/v1/wfs-flattened/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=csv"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","city-id","city-name","location","rating","is_open","created"
"{restaurant.id}","Café Noir","{restaurant.city_id}","CloudCity","{coordinates.point1_ewkt}","5.0","True","2020-04-05 12:11:10+00:00"
"{bad_restaurant.id}","Foo Bar","","","{coordinates.point2_ewkt}","1.0","False","2020-04-05 20:11:10+00:00"
""".lstrip()  # noqa: E501
        assert content == expect
        assert "SRID=4326;" in content

    def test_resource_id(self, client, restaurant, bad_restaurant):
        """Prove that fetching objects by ID works."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&RESOURCEID=restaurant.{restaurant.id}"
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
        restaurants = xml_doc.findall("wfs:member/app:restaurant", namespaces=NAMESPACES)
        names = [res.find("app:name", namespaces=NAMESPACES).text for res in restaurants]
        assert names == ["Café Noir"]

    def test_resource_id_unknown_id(self, client, restaurant, bad_restaurant):
        """Prove that unknown IDs simply return an empty list."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&RESOURCEID=restaurant.0"
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
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&RESOURCEID=restaurant.ABC"
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

    def test_resource_id_multiple(self, client, restaurant, bad_restaurant):
        """Prove that fetching multiple IDs works."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&RESOURCEID=restaurant.{restaurant.id},restaurant.{bad_restaurant.id}"
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
        restaurants = xml_doc.findall("wfs:member/app:restaurant", namespaces=NAMESPACES)
        names = [res.find("app:name", namespaces=NAMESPACES).text for res in restaurants]
        assert names == ["Café Noir", "Foo Bar"]

    def test_get_feature_by_id_stored_query(self, client, restaurant, bad_restaurant, coordinates):
        """Prove that fetching objects by ID works."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
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
            <gml:lowerCorner>{coordinates.point1_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point1_xml_wgs84}</gml:upperCorner>
        </gml:Envelope>
    </gml:boundedBy>
    <app:id>{restaurant.id}</app:id>
    <app:name>Café Noir</app:name>
    <app:city_id>{restaurant.city_id}</app:city_id>
    <app:location>
        <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
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

    def test_get_feature_by_id_bad_id(self, client, restaurant, bad_restaurant):
        """Prove that invalid IDs are properly handled."""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            "&ID=restaurant.ABC"
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
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            "&ID=restaurant.0"
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
