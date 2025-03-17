from urllib.parse import quote_plus

import django
import pytest
from django.db import OperationalError

from gisserver import conf, output
from tests.gisserver.views.input import GENERATED_FIELD_FILTER
from tests.requests import Get, Post, Url, parametrize_response
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
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
                <Query typeNames="restaurant">
                </Query>
                </GetFeature>
                """
        ),
    )
    def test_get_feature(self, restaurant, coordinates, response):
        """Prove that the happy flow works"""
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
          <gml:Point gml:id="Restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
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

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
              <Query typeNames="restaurant">
              </Query>
              </GetFeature>
              """
        ),
    )
    def test_get_empty_geometry(self, empty_restaurant, response):
        """Prove that the empty geometry values don't crash the rendering."""
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
          <app:restaurant gml:id="restaurant.{empty_restaurant.id}">
            <gml:name>Empty</gml:name>
            <app:id>{empty_restaurant.id}</app:id>
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

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=mini-restaurant"),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
              <Query typeNames="mini-restaurant">
              </Query>
              </GetFeature>
              """
        ),
    )
    def test_get_limited_fields(self, restaurant, coordinates, response):
        """Prove that the 'FeatureType(fields=..)' reduces the returned fields."""
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
          <gml:Point gml:id="Restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos srsDimension="2">{coordinates.point1_xml_wgs84}</gml:pos>
          </gml:Point>
        </app:location>
      </app:mini-restaurant>
    </wfs:member>
</wfs:FeatureCollection>""",  # noqa: E501
        )

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
              <Query typeNames="restaurant">
              </Query>
              </GetFeature>
              """
        ),
        url=Url.COMPLEX,
    )
    def test_get_complex(self, restaurant_m2m, bad_restaurant, coordinates, response):
        """Prove that rendering complex types works."""
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
          <gml:Point gml:id="Restaurant.{restaurant_m2m.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
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
          <gml:Point gml:id="Restaurant.{bad_restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
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

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
              <Query typeNames="restaurant">
              </Query>
              </GetFeature>
              """
        ),
        url=Url.FLAT,
    )
    def test_get_flattened(self, restaurant, bad_restaurant, coordinates, response):
        """Prove that rendering complex types works."""
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
        <app:city-region>OurRegion</app:city-region>
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
        <app:city-region xsi:nil="true" />
        <app:location>
          <gml:Point gml:id="Restaurant.{bad_restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
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

    def test_get_related_geometry(
        self,
        client,
        restaurant_review,
        bad_restaurant_review,
        restaurant_m2m,
        bad_restaurant,
        coordinates,
    ):
        """Prove that rendering complex types works."""

        response = client.get(
            "/v1/wfs-related-geometry/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&BBOX{coordinates.bbox}&TYPENAMES=restaurantReview&SORTBY=restaurant/name"
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
   xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs-related-geometry/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurantReview http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
   timeStamp="{timestamp}" numberMatched="2" numberReturned="2">

    <wfs:member>
      <app:restaurantReview gml:id="restaurantReview.{restaurant_review.id}">
        <gml:name>Café Noir: Pretty good!</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{coordinates.point1_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point1_xml_wgs84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{restaurant_review.id}</app:id>
        <app:restaurant>
          <app:id>{restaurant_m2m.id}</app:id>
          <app:name>Café Noir</app:name>
          <app:city>
            <app:id>{restaurant_m2m.city_id}</app:id>
            <app:name>CloudCity</app:name>
          </app:city>
          <app:location>
            <gml:Point gml:id="Restaurant.{restaurant_m2m.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
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
        <app:review>Pretty good!</app:review>
      </app:restaurantReview>
    </wfs:member>

    <wfs:member>
      <app:restaurantReview gml:id="restaurantReview.{bad_restaurant_review.id}">
        <gml:name>Foo Bar: Stay away!</gml:name>
        <gml:boundedBy>
          <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:lowerCorner>{coordinates.point2_xml_wgs84}</gml:lowerCorner>
            <gml:upperCorner>{coordinates.point2_xml_wgs84}</gml:upperCorner>
          </gml:Envelope>
        </gml:boundedBy>
        <app:id>{bad_restaurant_review.id}</app:id>
        <app:restaurant>
          <app:id>{bad_restaurant.id}</app:id>
          <app:name>Foo Bar</app:name>
          <app:city xsi:nil="true" />
          <app:location>
            <gml:Point gml:id="Restaurant.{bad_restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
              <gml:pos srsDimension="2">{coordinates.point2_xml_wgs84}</gml:pos>
            </gml:Point>
          </app:location>
          <app:rating>1.0</app:rating>
          <app:is_open>false</app:is_open>
          <app:created>2020-04-05T20:11:10+00:00</app:created>
        </app:restaurant>
        <app:review>Stay away!</app:review>
      </app:restaurantReview>
    </wfs:member>

</wfs:FeatureCollection>""",  # noqa: E501
        )

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&SRSNAME=urn:ogc:def:crs:EPSG::28992"
        ),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" srsName="urn:ogc:def:crs:EPSG::28992" {XML_NS}>
              <Query typeNames="restaurant">
              </Query>
              </GetFeature>
              """
        ),
    )
    def test_get_srs_name(self, restaurant, coordinates, response):
        """Prove that specifying SRSNAME works"""
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
              <gml:Point gml:id="Restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::28992">
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

    @pytest.mark.skipif(
        django.VERSION < (5, 0), reason="GeneratedField is only available in Django >= 5"
    )
    def test_get_works_with_generated_field(self, client, generated_field, coordinates):
        """Prove that we can fetch Generated Fields

        The `write_bounds` methods on the Renderers are patched, because it results in a
        boundedBy envelope that could not be deduced from the coordinates.
        """
        response = client.get(
            "/v1/wfs-gen-field/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&TYPENAMES=modelwithgeneratedfields"
            f"&FILTER={quote_plus(GENERATED_FIELD_FILTER['geometry_translated'].strip())}"
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
        feature = xml_doc.find("wfs:member/app:modelwithgeneratedfields", namespaces=NAMESPACES)
        assert feature is not None
        assert feature.find("app:name", namespaces=NAMESPACES).text == generated_field.name
        assert (
            feature.find("app:name_reversed", namespaces=NAMESPACES).text
            == generated_field.name_reversed
        )
        timestamp = xml_doc.attrib["timeStamp"]
        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns:gml="http://www.opengis.net/gml/3.2"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:app="http://example.org/gisserver" xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs-gen-field/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=modelwithgeneratedfields http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd" timeStamp="{timestamp}" numberMatched="1" numberReturned="1">
    <wfs:member>
        <app:modelwithgeneratedfields gml:id="modelwithgeneratedfields.{generated_field.id}">
            <gml:name>Palindrome</gml:name>
            <gml:boundedBy>
              <gml:Envelope srsDimension="2" srsName="urn:ogc:def:crs:EPSG::4326">
                <gml:lowerCorner>{coordinates.translated_xml_envelope[0]}</gml:lowerCorner>
                <gml:upperCorner>{coordinates.translated_xml_envelope[1]}</gml:upperCorner>
              </gml:Envelope>
            </gml:boundedBy>
            <app:id>{generated_field.id}</app:id>
            <app:name>Palindrome</app:name>
            <app:name_reversed>emordnilaP</app:name_reversed>
            <app:geometry>
                <gml:Point srsName="urn:ogc:def:crs:EPSG::4326" gml:id="ModelWithGeneratedFields.{generated_field.id}.1">
                    <gml:pos srsDimension="2">{coordinates.point1_xml_wgs84}</gml:pos>
                </gml:Point>
            </app:geometry>
            <app:geometry_translated>
                <gml:Point srsName="urn:ogc:def:crs:EPSG::4326" gml:id="ModelWithGeneratedFields.{generated_field.id}.2">
                    <gml:pos srsDimension="2">{coordinates.translated_xml_wgs84}</gml:pos>
                </gml:Point>
            </app:geometry_translated>
        </app:modelwithgeneratedfields>
    </wfs:member>
</wfs:FeatureCollection>""",  # noqa: E501
        )

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant&RESULTTYPE=hits"),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" resultType="hits" {XML_NS}>
              <Query typeNames="restaurant">
              </Query>
              </GetFeature>
              """
        ),
    )
    @pytest.mark.parametrize("use_count", [1, 0])
    def test_get_hits(self, restaurant, use_count, monkeypatch, response):
        """Prove that that parsing RESULTTYPE=hits works"""
        monkeypatch.setattr(conf, "GISSERVER_COUNT_NUMBER_MATCHED", use_count)
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

    @parametrize_response(
        Get(
            lambda start_index: "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            f"&SORTBY=name&vendor-arg=foobar&COUNT=1&STARTINDEX={start_index}",
            expect={
                "next": "http://testserver/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&SORTBY=name"
                "&vendor-arg=foobar"
                "&COUNT=1&STARTINDEX=1",
                "previous": "http://testserver/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&SORTBY=name"
                "&vendor-arg=foobar"
                "&COUNT=1&STARTINDEX=0",
            },
        ),
        Post(
            lambda start_index: f"""<GetFeature service="WFS" version="2.0.0" {XML_NS} count="1" startIndex="{start_index}">
                    <Query typeNames="restaurant">
                    <fes:SortBy>
                        <fes:SortProperty>
                            <fes:ValueReference>name</fes:ValueReference>
                            <fes:SortOrder>ASC</fes:SortOrder>
                        </fes:SortProperty>
                    </fes:SortBy>
                    </Query>
                    </GetFeature>
                    """,
            expect={
                "next": "http://testserver/v1/wfs/",
                "previous": "http://testserver/v1/wfs/",
            },
        ),
    )
    @pytest.mark.parametrize("use_count", [1, 0])
    def test_pagination(
        self,
        restaurant,
        bad_restaurant,
        use_count,
        monkeypatch,
        django_assert_max_num_queries,
        response,
    ):
        """Prove that that pagination works.

        Two variations are tested; when normal COUNT happens,
        or a sentinel object is used to detect there are more results.
        """
        monkeypatch.setattr(conf, "GISSERVER_COUNT_NUMBER_MATCHED", use_count)
        names = []
        for start_index in range(4):  # test whether last page stops
            with django_assert_max_num_queries(1 + use_count):
                res = response(start_index)
                content = read_response(res)
            assert res["content-type"] == "text/xml; charset=utf-8", content
            assert res.status_code == 200, content
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
                assert xml_doc.attrib.get("previous") == response.expect["previous"]
                break  # last page reached

            assert next_url == response.expect["next"]

        # Prove that both items were returned
        assert len(names) == 2
        assert names[0] != names[1]

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"),
        Post(
            f"""<GetFeature service="WFS" version="2.0.0" {XML_NS}>
              <Query typeNames="restaurant">
              </Query>
              </GetFeature>
              """
        ),
    )
    def test_truncated_response(self, restaurant, monkeypatch, response):
        """Prove that errors are properly handled during streaming."""

        def _mock_error(*args, **kwargs):
            raise OperationalError("Mocked Database Error")

        monkeypatch.setattr(output.GML32Renderer, "start_collection", _mock_error)
        content_parts = []
        with pytest.raises(OperationalError):
            for part in response:
                content_parts.append(part)

        content = b"".join(content_parts)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content  # rendering started before errors

        xml_doc = validate_xsd(content, WFS_20_XSD)
        timestamp = xml_doc.attrib["timeStamp"]

        print(content.decode("utf-8"))
        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection
             xmlns:app="http://example.org/gisserver"
             xmlns:gml="http://www.opengis.net/gml/3.2"
             xmlns:wfs="http://www.opengis.net/wfs/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
             timeStamp="{timestamp}" numberMatched="1" numberReturned="1">
              <wfs:truncatedResponse>
                <ows:ExceptionReport
                    xmlns:ows="http://www.opengis.net/ows/1.1"
                    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                    xsi:schemaLocation="http://www.opengis.net/ows/1.1 http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd"
                    xml:lang="en-US" version="2.0.0">
                  <ows:Exception exceptionCode="OperationalError">

                     <ows:ExceptionText>OperationalError during rendering!</ows:ExceptionText>

                  </ows:Exception>
                </ows:ExceptionReport>
              </wfs:truncatedResponse>
            </wfs:FeatureCollection>
        """,
        )
