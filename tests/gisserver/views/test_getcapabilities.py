import re
from urllib.parse import quote_plus

import pytest
from lxml import etree

from gisserver.parsers.xml import xmlns
from tests.requests import Get, Post, Url, parametrize_response
from tests.utils import NAMESPACES, WFS_20_XSD, XML_NS, assert_xml_equal, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]

gml32 = quote_plus("application/gml+xml; version=3.2")


@pytest.mark.django_db
class TestGetCapabilities:
    """All tests for the GetCapabilities method."""

    @parametrize_response(
        Get(f"?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=2.0.0&OUTPUTFORMAT={gml32}"),
        Post(
            f"""<GetCapabilities service="WFS" {XML_NS}>
            <ows:AcceptVersions><ows:Version>2.0.0</ows:Version></ows:AcceptVersions>
        </GetCapabilities>"""
        ),
    )
    def test_get(self, restaurant, coordinates, response):
        """Prove that the happy flow works"""
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "<ows:OperationsMetadata>" in content

        # assert both GET and POST methods are available for all 6 wfs requests.
        get = re.compile("ows:Get")
        post = re.compile("ows:Post")
        assert len(get.findall(content)) == 6
        assert len(post.findall(content)) == 6

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

        assert_xml_equal(
            etree.tostring(feature_type_list, inclusive_ns_prefixes=True).decode(),
            f"""<FeatureTypeList xmlns="{xmlns.wfs}" xmlns:ows="{xmlns.ows11}" xmlns:xlink="{xmlns.xlink}">
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
          <ows:LowerCorner>{coordinates.point1_xml_wgs84_bbox}</ows:LowerCorner>
          <ows:UpperCorner>{coordinates.point1_xml_wgs84_bbox}</ows:UpperCorner>
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
          <ows:LowerCorner>{coordinates.point1_xml_wgs84_bbox}</ows:LowerCorner>
          <ows:UpperCorner>{coordinates.point1_xml_wgs84_bbox}</ows:UpperCorner>
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

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=1.0.0,2.0.0"),
        Post(
            f"""<GetCapabilities service="WFS" {XML_NS}>
              <ows:AcceptVersions>
                <ows:Version>1.0.0</ows:Version>
                <ows:Version>2.0.0</ows:Version>
              </ows:AcceptVersions>
            </GetCapabilities>"""
        ),
    )
    def test_version_negotiation(self, response):
        """Prove that version negotiation still returns 2.0.0"""
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content

        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=1.5.0"),
        Post(
            f'<GetCapabilities service="WFS" {XML_NS}>'
            "  <ows:AcceptVersions>"
            "    <ows:Version>1.5.0</ows:Version>"
            "  </ows:AcceptVersions>"
            "</GetCapabilities>"
        ),
    )
    def test_get_invalid_version(self, response):
        """Prove that version negotiation works"""
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content

        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "VersionNegotiationFailed"

    @parametrize_response(
        Get(
            f"?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=2.0.0&OUTPUTFORMAT={gml32}",
        ),
        Post(
            f"""<GetCapabilities service="WFS" {XML_NS}>
              <ows:AcceptVersions><ows:Version>2.0.0</ows:Version></ows:AcceptVersions>
            </GetCapabilities>""",
        ),
        url=Url.FLAT,
    )
    def test_get_flattened(self, restaurant, coordinates, response):
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "<ows:OperationsMetadata>" in content
        assert '<ows:WGS84BoundingBox dimensions="2">' in content
