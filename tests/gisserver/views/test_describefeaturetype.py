import pytest
from lxml import etree

from tests.constants import NAMESPACES
from tests.utils import WFS_20_XSD, assert_xml_equal, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


class TestDescribeFeatureType:
    """All tests for the DescribeFeatureType method."""

    def test_describe(self, client):
        """Prove that the happy flow works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=restaurant"
        )
        content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself.
        # Only validate it's XML structure
        xml_doc: etree._Element = etree.fromstring(response.content)
        assert xml_doc.tag == "{http://www.w3.org/2001/XMLSchema}schema"
        elements = xml_doc.findall(
            "xsd:complexType/xsd:complexContent/xsd:extension/xsd:sequence/xsd:element",
            namespaces=NAMESPACES,
        )
        field_names = [el.attrib["name"] for el in elements]
        assert field_names == ["id", "name", "city_id", "location", "rating", "created"]

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
          <element name="created" type="dateTime" minOccurs="0" />
        </sequence>
      </extension>
    </complexContent>
  </complexType>

</schema>""",  # noqa: E501
        )

    def test_describe_complex(self, client):
        """Prove that complex types are properly rendered"""
        response = client.get(
            "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0"
            "&TYPENAMES=restaurant"
        )
        content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself.
        # Only validate it's XML structure
        xml_doc: etree._Element = etree.fromstring(response.content)
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
          <element name="created" type="dateTime" minOccurs="0" />
        </sequence>
      </extension>
    </complexContent>
  </complexType>

  <complexType name="CityType">
    <complexContent>
      <extension base="gml:AbstractFeatureType">
        <sequence>
          <element name="id" type="integer" minOccurs="0" />
          <element name="name" type="string" minOccurs="0" />
        </sequence>
      </extension>
    </complexContent>
  </complexType>

</schema>""",  # noqa: E501
        )

    def test_describe_flattened(self, client):
        """Prove that complex types are properly rendered"""
        response = client.get(
            "/v1/wfs-flattened/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0"
            "&TYPENAMES=restaurant"
        )
        content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself.
        # Only validate it's XML structure
        xml_doc: etree._Element = etree.fromstring(response.content)
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
          <element name="location" type="gml:PointPropertyType" minOccurs="0" maxOccurs="1" nillable="true" />
          <element name="rating" type="double" minOccurs="0" />
          <element name="created" type="dateTime" minOccurs="0" />
        </sequence>
      </extension>
    </complexContent>
  </complexType>

</schema>""",  # noqa: E501
        )

    def test_empty_typenames(self, client):
        """Prove that missing arguments are handled"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES="
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "MissingParameterValue"

    def test_all_typenames(self, client):
        """Prove that the happy flow works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0"
        )
        content = response.content.decode()
        # assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "PropertyType" in content  # for element holding a GML field

        # The response is an XSD itself.
        # Only validate it's XML structure
        xml_doc: etree._Element = etree.fromstring(response.content)
        assert xml_doc.tag == "{http://www.w3.org/2001/XMLSchema}schema"
