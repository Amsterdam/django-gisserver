import urllib.parse

import django
import pytest

from tests.requests import Get, Post, Url, parametrize_response
from tests.utils import (
    NAMESPACES,
    WFS_20_XSD,
    XML_NS,
    XMLSCHEMA_XSD,
    assert_xml_equal,
    validate_xsd,
)

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]
gml32 = urllib.parse.quote_plus("application/gml+xml; version=3.2")


class TestDescribeFeatureType:
    """All tests for the DescribeFeatureType method."""

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=restaurant"),
        Post(
            f"""<DescribeFeatureType version="2.0.0" service="WFS" {XML_NS}>
              <TypeName>restaurant</TypeName>
              </DescribeFeatureType>
              """
        ),
    )
    def test_describe(self, response):
        """Prove that the happy flow works"""
        content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself, this too can be validated against its own XSD.
        xml_doc = validate_xsd(response.content, XMLSCHEMA_XSD)
        assert xml_doc.tag == "{http://www.w3.org/2001/XMLSchema}schema"
        elements = xml_doc.findall(
            "xsd:complexType/xsd:complexContent/xsd:extension/xsd:sequence/xsd:element",
            namespaces=NAMESPACES,
        )
        field_names = [el.attrib["name"] for el in elements]
        assert field_names == [
            "id",
            "name",
            "city_id",
            "location",
            "rating",
            "is_open",
            "created",
            "tags",
        ]

        assert_xml_equal(
            response.content,
            """<schema
   targetNamespace="http://example.org/gisserver"
   xmlns:app="http://example.org/gisserver"
   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
   xmlns="http://www.w3.org/2001/XMLSchema"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   elementFormDefault="qualified" version="0.1">

  <import namespace="http://www.opengis.net/gml/3.2" schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd" />

  <element name="restaurant" type="app:RestaurantType" substitutionGroup="gml:AbstractFeature" />

  <complexType name="RestaurantType">
    <complexContent>
      <extension base="gml:AbstractFeatureType">
        <sequence>
          <element name="id" type="integer" minOccurs="0" />
          <element name="name" type="string" minOccurs="0" />
          <element name="city_id" type="integer" nillable="true" minOccurs="0" />
          <element name="location" type="gml:PointPropertyType" nillable="true" minOccurs="0" maxOccurs="1"/>
          <element name="rating" type="double" minOccurs="0" />
          <element name="is_open" type="boolean" minOccurs="0" />
          <element name="created" type="dateTime" minOccurs="0" />
          <element name="tags" type="string" minOccurs="0" maxOccurs="unbounded" nillable="true" />
        </sequence>
      </extension>
    </complexContent>
  </complexType>

</schema>""",  # noqa: E501
        )

    @pytest.mark.skipif(
        django.VERSION < (5, 0), reason="GeneratedField is only available in Django >= 5"
    )
    def test_describe_generated_field(self, client):
        """Prove that the happy flow works"""
        response = client.get(
            "/v1/wfs-gen-field/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=modelwithgeneratedfields"
        )
        content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself, this too can be validated against its own XSD.
        xml_doc = validate_xsd(response.content, XMLSCHEMA_XSD)
        assert xml_doc.tag == "{http://www.w3.org/2001/XMLSchema}schema"
        elements = xml_doc.findall(
            "xsd:complexType/xsd:complexContent/xsd:extension/xsd:sequence/xsd:element",
            namespaces=NAMESPACES,
        )
        field_names = [el.attrib["name"] for el in elements]
        assert field_names == [
            "id",
            "name",
            "name_reversed",
            "geometry",
            "geometry_translated",
        ]

        assert_xml_equal(
            response.content,
            """<schema
   targetNamespace="http://example.org/gisserver"
   xmlns:app="http://example.org/gisserver"
   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
   xmlns="http://www.w3.org/2001/XMLSchema"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   elementFormDefault="qualified" version="0.1">

  <import namespace="http://www.opengis.net/gml/3.2" schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd" />

  <element name="modelwithgeneratedfields" type="app:ModelwithgeneratedfieldsType" substitutionGroup="gml:AbstractFeature" />

  <complexType name="ModelwithgeneratedfieldsType">
    <complexContent>
      <extension base="gml:AbstractFeatureType">
        <sequence>
          <element name="id" type="integer" minOccurs="0" />
          <element name="name" type="string" minOccurs="0" />
          <element name="name_reversed" type="string" minOccurs="0" />
          <element name="geometry" type="gml:PointPropertyType" nillable="true" minOccurs="0" maxOccurs="1"/>
          <element name="geometry_translated" type="gml:PointPropertyType" nillable="true" minOccurs="0" maxOccurs="1"/>
        </sequence>
      </extension>
    </complexContent>
  </complexType>

</schema>""",  # noqa: E501
        )

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=restaurant"),
        Post(
            f"""<DescribeFeatureType version="2.0.0" service="WFS" {XML_NS}>
                <TypeName>restaurant</TypeName>
              </DescribeFeatureType>
              """
        ),
        url=Url.COMPLEX,
    )
    def test_describe_complex(self, response):
        """Prove that complex types are properly rendered"""
        content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself, this too can be validated against its own XSD.
        xml_doc = validate_xsd(response.content, XMLSCHEMA_XSD)
        assert xml_doc.tag == "{http://www.w3.org/2001/XMLSchema}schema"

        assert_xml_equal(
            response.content,
            """<schema
   xmlns="http://www.w3.org/2001/XMLSchema"
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   targetNamespace="http://example.org/gisserver"
   elementFormDefault="qualified" version="0.1">

  <import namespace="http://www.opengis.net/gml/3.2" schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd" />

  <element name="restaurant" type="app:RestaurantType" substitutionGroup="gml:AbstractFeature" />

  <complexType name="RestaurantType">
    <complexContent>
      <extension base="gml:AbstractFeatureType">
        <sequence>
          <element name="id" type="integer" minOccurs="0" />
          <element name="name" type="string" minOccurs="0" />
          <element name="city" type="app:CityType" minOccurs="0" nillable="true" />
          <element name="location" type="gml:PointPropertyType" minOccurs="0" maxOccurs="1" nillable="true" />
          <element name="rating" type="double" minOccurs="0" />
          <element name="is_open" type="boolean" minOccurs="0" />
          <element name="created" type="dateTime" minOccurs="0" />
          <element name="opening_hours" type="app:OpeningHourType" minOccurs="0" maxOccurs="unbounded" />
          <element name="tags" type="string" minOccurs="0" maxOccurs="unbounded" nillable="true" />
        </sequence>
      </extension>
    </complexContent>
  </complexType>

  <complexType name="CityType">
    <sequence>
      <element name="id" type="integer" minOccurs="0" />
      <element name="name" type="string" minOccurs="0" />
    </sequence>
  </complexType>

  <complexType name="OpeningHourType">
    <sequence>
      <element name="weekday" type="integer" minOccurs="0" />
      <element name="start_time" type="time" minOccurs="0" />
      <element name="end_time" type="time" minOccurs="0" />
    </sequence>
  </complexType>

</schema>
""",  # noqa: E501
        )

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=restaurant"),
        Post(
            f"""<DescribeFeatureType version="2.0.0" service="WFS" {XML_NS}>
                <TypeName>restaurant</TypeName>
              </DescribeFeatureType>
              """
        ),
        url=Url.FLAT,
    )
    def test_describe_flattened(self, response):
        """Prove that complex types are properly rendered"""
        content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself, this too can be validated against its own XSD.
        xml_doc = validate_xsd(response.content, XMLSCHEMA_XSD)
        assert xml_doc.tag == "{http://www.w3.org/2001/XMLSchema}schema"

        assert_xml_equal(
            response.content,
            """<schema
   xmlns="http://www.w3.org/2001/XMLSchema"
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   targetNamespace="http://example.org/gisserver"
   elementFormDefault="qualified" version="0.1">

  <import namespace="http://www.opengis.net/gml/3.2" schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd" />

  <element name="restaurant" type="app:RestaurantType" substitutionGroup="gml:AbstractFeature" />

  <complexType name="RestaurantType">
    <complexContent>
      <extension base="gml:AbstractFeatureType">
        <sequence>
          <element name="id" type="integer" minOccurs="0" />
          <element name="name" type="string" minOccurs="0" />
          <element name="city-id" type="integer" minOccurs="0" nillable="true" />
          <element name="city-name" type="string" minOccurs="0" nillable="true" />
          <element name="city-region" type="string" minOccurs="0" nillable="true" />
          <element name="location" type="gml:PointPropertyType" minOccurs="0" maxOccurs="1" nillable="true" />
          <element name="rating" type="double" minOccurs="0" />
          <element name="is_open" type="boolean" minOccurs="0" />
          <element name="created" type="dateTime" minOccurs="0" />
          <element name="tags" type="string" minOccurs="0" maxOccurs="unbounded" nillable="true" />
        </sequence>
      </extension>
    </complexContent>
  </complexType>

</schema>""",  # noqa: E501
        )

    def test_describe_related_geometry(self, client):
        """Prove that complex types are properly rendered"""
        response = client.get(
            "/v1/wfs-related-geometry/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0"
            "&TYPENAMES=restaurantReview"
        )
        content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself, this too can be validated against its own XSD.
        xml_doc = validate_xsd(response.content, XMLSCHEMA_XSD)
        assert xml_doc.tag == "{http://www.w3.org/2001/XMLSchema}schema"
        assert_xml_equal(
            response.content,
            """<schema
   xmlns="http://www.w3.org/2001/XMLSchema"
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   targetNamespace="http://example.org/gisserver"
   elementFormDefault="qualified" version="0.1">

  <import namespace="http://www.opengis.net/gml/3.2" schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd" />

  <element name="restaurantReview" type="app:RestaurantReviewType" substitutionGroup="gml:AbstractFeature" />

  <complexType name="RestaurantReviewType">
    <complexContent>
      <extension base="gml:AbstractFeatureType">
        <sequence>
          <element name="id" type="integer" minOccurs="0" />
          <element name="restaurant" type="app:RestaurantType" minOccurs="0" />
          <element name="review" type="string" minOccurs="0" />
        </sequence>
      </extension>
    </complexContent>
  </complexType>

  <complexType name="RestaurantType">
    <complexContent>
      <extension base="gml:AbstractFeatureType">
        <sequence>
          <element name="id" type="integer" minOccurs="0" />
          <element name="name" type="string" minOccurs="0" />
          <element name="city" type="app:CityType" minOccurs="0" nillable="true" />
          <element name="location" type="gml:PointPropertyType" minOccurs="0" maxOccurs="1" nillable="true" />
          <element name="rating" type="double" minOccurs="0" />
          <element name="is_open" type="boolean" minOccurs="0" />
          <element name="created" type="dateTime" minOccurs="0" />
          <element name="opening_hours" type="app:OpeningHourType" minOccurs="0" maxOccurs="unbounded" />
          <element name="tags" type="string" minOccurs="0" maxOccurs="unbounded" nillable="true" />
        </sequence>
      </extension>
    </complexContent>
  </complexType>

  <complexType name="CityType">
    <sequence>
      <element name="id" type="integer" minOccurs="0" />
      <element name="name" type="string" minOccurs="0" />
    </sequence>
  </complexType>

  <complexType name="OpeningHourType">
    <sequence>
      <element name="weekday" type="integer" minOccurs="0" />
      <element name="start_time" type="time" minOccurs="0" />
      <element name="end_time" type="time" minOccurs="0" />
    </sequence>
  </complexType>

</schema>""",  # noqa: E501
        )

    @parametrize_response(
        Get(
            f"?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=restaurant&outputformat={gml32}"
        ),
        Post(
            f"""<DescribeFeatureType version="2.0.0" service="WFS" outputFormat="application/gml+xml; version=3.2" {XML_NS}>
                <TypeName>restaurant</TypeName>
              </DescribeFeatureType>
              """
        ),
    )
    def test_describe_outputformat(self, response):
        """Test workaround for FME's outputformat."""
        content = response.content.decode()
        assert response.status_code == 200, content

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES="),
        Post(
            f"""<DescribeFeatureType version="2.0.0" service="WFS" {XML_NS}>
              <TypeName></TypeName>
              </DescribeFeatureType>
              """,
            validate_xml=False,
        ),
    )
    def test_empty_typenames(self, response):
        """Prove that missing arguments are handled"""
        content = response.content.decode()
        assert response.status_code == 400, content
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "MissingParameterValue"

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0"),
        Post(
            f"""<DescribeFeatureType version="2.0.0" service="WFS"  {XML_NS}>
              </DescribeFeatureType>
              """
        ),
    )
    def test_all_typenames(self, response):
        """Prove that the happy flow works"""
        content = response.content.decode()
        # assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself, this too can be validated against its own XSD.
        xml_doc = validate_xsd(response.content, XMLSCHEMA_XSD)
        assert xml_doc.tag == "{http://www.w3.org/2001/XMLSchema}schema"
