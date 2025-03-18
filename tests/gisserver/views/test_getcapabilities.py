from urllib.parse import quote_plus

import pytest
from lxml import etree

from gisserver.parsers.xml import xmlns
from tests.utils import NAMESPACES, WFS_20_XSD, assert_xml_equal, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetCapabilities:
    """All tests for the GetCapabilities method."""

    def test_get(self, client, restaurant, coordinates):
        """Prove that the happy flow works"""
        gml32 = quote_plus("application/gml+xml; version=3.2")
        response = client.get(
            f"/v1/wfs/?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=2.0.0&OUTPUTFORMAT={gml32}"
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "<ows:OperationsMetadata>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"

        # Check exposed allowed versions
        allowed_values = xml_doc.xpath(
            "ows:OperationsMetadata/ows:Operation[@name='GetCapabilities']"
            "/ows:Parameter[@name='AcceptVersions']/ows:AllowedValues",
            namespaces=NAMESPACES,
        )[0]
        versions = [el.text for el in allowed_values.findall("ows:Value", NAMESPACES)]
        assert versions == ["2.0.0"]

        # Check exposed FeatureTypeList
        feature_type_list = xml_doc.find("wfs:FeatureTypeList", NAMESPACES)

        # The box should be within WGS84 limits, otherwise gis tools can't process the service.
        wgs84_bbox = feature_type_list.find("wfs:FeatureType/ows:WGS84BoundingBox", NAMESPACES)
        lower = wgs84_bbox.find("ows:LowerCorner", NAMESPACES).text.split(" ")
        upper = wgs84_bbox.find("ows:UpperCorner", NAMESPACES).text.split(" ")
        coords = list(map(float, lower + upper))
        assert coords[0] >= -180
        assert coords[1] >= -90
        assert coords[2] <= 180
        assert coords[2] <= 90

        assert_xml_equal(
            etree.tostring(feature_type_list, inclusive_ns_prefixes=True).decode(),
            f"""<FeatureTypeList xmlns="{xmlns.wfs}" xmlns:ows="{xmlns.ows}" xmlns:xlink="{xmlns.xlink}">
      <FeatureType>
        <Name>app:restaurant</Name>
        <Title>restaurant</Title>
        <ows:Keywords>
          <ows:Keyword>unittest</ows:Keyword>
        </ows:Keywords>
        <DefaultCRS>urn:ogc:def:crs:EPSG::4326</DefaultCRS>
        <OtherCRS>urn:ogc:def:crs:EPSG::28992</OtherCRS>
        <OutputFormats>
          <Format>application/gml+xml; version=3.2</Format>
          <Format>text/xml; subtype=gml/3.2.1</Format>
          <Format>application/json; subtype=geojson; charset=utf-8</Format>
          <Format>geojson</Format>
          <Format>text/csv; subtype=csv; charset=utf-8</Format>
        </OutputFormats>
        <ows:WGS84BoundingBox dimensions="2">
          <ows:LowerCorner>{coordinates.point1_xml_wgs84}</ows:LowerCorner>
          <ows:UpperCorner>{coordinates.point1_xml_wgs84}</ows:UpperCorner>
        </ows:WGS84BoundingBox>
        <MetadataURL xlink:href="http://testserver/v1/wfs/" />
      </FeatureType>
      <FeatureType>
        <Name>app:mini-restaurant</Name>
        <Title>restaurant</Title>
        <ows:Keywords>
          <ows:Keyword>unittest</ows:Keyword>
          <ows:Keyword>limited-fields</ows:Keyword>
        </ows:Keywords>
        <DefaultCRS>urn:ogc:def:crs:EPSG::4326</DefaultCRS>
        <OtherCRS>urn:ogc:def:crs:EPSG::28992</OtherCRS>
        <OutputFormats>
          <Format>application/gml+xml; version=3.2</Format>
          <Format>text/xml; subtype=gml/3.2.1</Format>
          <Format>application/json; subtype=geojson; charset=utf-8</Format>
          <Format>geojson</Format>
          <Format>text/csv; subtype=csv; charset=utf-8</Format>
        </OutputFormats>
        <ows:WGS84BoundingBox dimensions="2">
          <ows:LowerCorner>{coordinates.point1_xml_wgs84}</ows:LowerCorner>
          <ows:UpperCorner>{coordinates.point1_xml_wgs84}</ows:UpperCorner>
        </ows:WGS84BoundingBox>
        <MetadataURL xlink:href="http://testserver/v1/wfs/" />
      </FeatureType>
      <FeatureType>
        <Name>app:denied-feature</Name>
        <Title>restaurant</Title>
        <DefaultCRS>urn:ogc:def:crs:EPSG::4326</DefaultCRS>
        <OutputFormats>
          <Format>application/gml+xml; version=3.2</Format>
          <Format>text/xml; subtype=gml/3.2.1</Format>
          <Format>application/json; subtype=geojson; charset=utf-8</Format>
          <Format>geojson</Format>
          <Format>text/csv; subtype=csv; charset=utf-8</Format>
        </OutputFormats>
      </FeatureType>
    </FeatureTypeList>""",
        )

    def test_missing_parameters(self, client):
        """Prove that missing arguments are handled"""
        response = client.get("/v1/wfs/?SERVICE=WFS")
        content = response.content.decode()
        assert response.status_code == 400, content
        assert response["content-type"] == "text/xml; charset=utf-8", content

        assert_xml_equal(
            response.content,
            """<ows:ExceptionReport version="2.0.0"
 xmlns:ows="http://www.opengis.net/ows/1.1"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xml:lang="en-US"
 xsi:schemaLocation="http://www.opengis.net/ows/1.1 http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd">

  <ows:Exception exceptionCode="MissingParameterValue" locator="request">
    <ows:ExceptionText>Missing required &#x27;request&#x27; parameter.</ows:ExceptionText>
  </ows:Exception>
</ows:ExceptionReport>""",  # noqa: E501
        )

        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "MissingParameterValue"

    def test_version_negotiation(self, client):
        """Prove that version negotiation still returns 2.0.0"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=1.0.0,2.0.0"
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content

        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"

    def test_get_invalid_version(self, client):
        """Prove that version negotiation works"""
        response = client.get("/v1/wfs/?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=1.5.0")
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content

        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "VersionNegotiationFailed"

    def test_get_flattened(self, client, restaurant, coordinates):
        gml32 = quote_plus("application/gml+xml; version=3.2")
        response = client.get(
            f"/v1/wfs-flattened/?SERVICE=WFS&REQUEST=GetCapabilities&"
            f"ACCEPTVERSIONS=2.0.0&OUTPUTFORMAT={gml32}"
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "<ows:OperationsMetadata>" in content
        assert '<ows:WGS84BoundingBox dimensions="2">' in content
