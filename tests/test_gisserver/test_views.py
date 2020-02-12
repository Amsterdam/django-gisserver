import pytest
from django.urls import path
from lxml import etree

from gisserver.features import FeatureType, ServiceDescription
from gisserver.types import WGS84, CRS
from gisserver.views import WFSView

from .models import Restaurant
from .utils import WFS_20_XSD, assert_xml_equal, validate_xsd

WFS_NS = "http://www.opengis.net/wfs/2.0"
OWS_NS = "http://www.opengis.net/ows/1.1"
XLINK_NS = "http://www.w3.org/1999/xlink"
NAMESPACES = {
    "app": "http://example.org/gisserver",
    "gml": "http://www.opengis.net/gml/3.2",
    "ows": "http://www.opengis.net/ows/1.1",
    "wfs": "http://www.opengis.net/wfs/2.0",
    "xsd": "http://www.w3.org/2001/XMLSchema",
}

RD_NEW = CRS.from_string("urn:ogc:def:crs:EPSG::28992")


class PlacesWFSView(WFSView):
    """An simple view that uses the WFSView against our test model."""

    xml_namespace = "http://example.org/gisserver"
    service_description = ServiceDescription(
        # While not tested directly, this is still validated against the XSD
        title="Places",
        abstract="Unittesting",
        keywords=["django-gisserver"],
        provider_name="Django",
        provider_site="https://www.example.com/",
        contact_person="django-gisserver",
    )
    feature_types = [
        FeatureType(
            Restaurant,
            keywords=["unittest"],
            other_crs=[RD_NEW],
            metadata_url="/feature/restaurants/",
        ),
    ]


urlpatterns = [
    path("v1/wfs/", PlacesWFSView.as_view(), name="wfs-view"),
]

pytestmark = [pytest.mark.urls(__name__)]  # enable for all tests in this file


@pytest.mark.django_db
class TestGetCapabilities:
    """All tests for the GetCapabilities method."""

    def test_get(self, client, restaurant):
        """Prove that the happy flow works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=2.0.0"
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "<ows:OperationsMetadata>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"

        # Check exposed allowed vesions
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
        wgs84_bbox = feature_type_list.find(
            "wfs:FeatureType/ows:WGS84BoundingBox", NAMESPACES
        )
        lower = wgs84_bbox.find("ows:LowerCorner", NAMESPACES).text.split(" ")
        upper = wgs84_bbox.find("ows:UpperCorner", NAMESPACES).text.split(" ")
        coords = list(map(float, lower + upper))
        assert coords[0] >= -180
        assert coords[1] >= -90
        assert coords[2] <= 180
        assert coords[2] <= 90

        assert_xml_equal(
            etree.tostring(feature_type_list, inclusive_ns_prefixes=True).decode(),
            f"""<FeatureTypeList xmlns="{WFS_NS}" xmlns:ows="{OWS_NS}" xmlns:xlink="{XLINK_NS}">
      <FeatureType>
        <Name>restaurant</Name>
        <Title>restaurant</Title>
        <ows:Keywords>
          <ows:Keyword>unittest</ows:Keyword>
        </ows:Keywords>
        <DefaultCRS>urn:ogc:def:crs:EPSG::4326</DefaultCRS>
        <OtherCRS>urn:ogc:def:crs:EPSG::28992</OtherCRS>
        <OutputFormats>
          <Format>text/xml; subtype=gml/3.1.1</Format>
          <Format>application/json; subtype=geojson; charset=utf-8</Format>
        </OutputFormats>
        <ows:WGS84BoundingBox dimensions="2">
          <ows:LowerCorner>4.90876101285122 52.3631712637357</ows:LowerCorner>
          <ows:UpperCorner>4.90876101285122 52.3631712637357</ows:UpperCorner>
        </ows:WGS84BoundingBox>
        <MetadataURL xlink:href="http://testserver/v1/wfs/" />
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
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=1.5.0"
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content

        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "VersionNegotiationFailed"


class TestDescribeFeatureType:
    """All tests for the DescribeFeatureType method."""

    def test_get(self, client):
        """Prove that the happy flow works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=restaurant"
        )
        content = response.content.decode()
        assert response["content-type"] == "application/gml+xml; version=3.2", content
        assert response.status_code == 200, content
        assert "gml:GeometryPropertyType" in content

        # The response is an XSD itself.
        # Only validate it's XML structure
        xml_doc: etree._Element = etree.fromstring(response.content)
        assert xml_doc.tag == "{http://www.w3.org/2001/XMLSchema}schema"
        elements = xml_doc.findall(
            "xsd:complexType/xsd:complexContent/xsd:extension/xsd:sequence/xsd:element",
            namespaces=NAMESPACES,
        )
        field_names = [el.attrib["name"] for el in elements]
        assert field_names == ["id", "name", "location"]

        assert_xml_equal(
            response.content,
            """<schema
   targetNamespace="http://example.org/gisserver"
   xmlns:app="http://example.org/gisserver"
   xmlns:xsd="http://www.w3.org/2001/XMLSchema"
   xmlns="http://www.w3.org/2001/XMLSchema"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   elementFormDefault="qualified" version="0.1" >

  <import namespace="http://www.opengis.net/gml/3.2" schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd" />
  <element name="restaurant" type="app:restaurantType" substitutionGroup="gml:AbstractFeature" />

  <complexType name="restaurantType">
    <complexContent>
      <extension base="gml:AbstractFeatureType">
        <sequence>
          <element name="id" minOccurs="0" type="integer"/>
          <element name="name" minOccurs="0" type="string"/>
          <element name="location" type="gml:GeometryPropertyType" minOccurs="0" maxOccurs="1"/>
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


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    def test_get(self, client, restaurant):
        """Prove that the happy flow works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # See whether our feature is rendered
        feature = xml_doc.find("wfs:member/app:restaurant", namespaces=NAMESPACES)
        assert feature is not None
        assert feature.find("app:name", namespaces=NAMESPACES).text == restaurant.name
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            response.content,
            f"""<wfs:FeatureCollection
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   xmlns:wfs="http://www.opengis.net/wfs/2.0"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
   timeStamp="{timestamp}" numberMatched="1" numberReturned="1">

    <wfs:member>
      <app:restaurant gml:id="restaurant.{restaurant.id}">
        <gml:boundedBy>
            <gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">
                <gml:lowerCorner>4.908761012851219 52.363171263735715</gml:lowerCorner>
                <gml:upperCorner>4.908761012851219 52.363171263735715</gml:upperCorner>
            </gml:Envelope>
        </gml:boundedBy>
        <app:id>{restaurant.id}</app:id>
        <app:name>Café Noir</app:name>
        <app:location>
          <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos>4.908761012851219 52.363171263735715</gml:pos>
          </gml:Point>
        </app:location>
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
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        feature = xml_doc.find("wfs:member/app:restaurant", namespaces=NAMESPACES)
        assert feature.find("app:location", namespaces=NAMESPACES).text is None
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            response.content,
            f"""<wfs:FeatureCollection
       xmlns:app="http://example.org/gisserver"
       xmlns:gml="http://www.opengis.net/gml/3.2"
       xmlns:wfs="http://www.opengis.net/wfs/2.0"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
       timeStamp="{timestamp}" numberMatched="1" numberReturned="1">

        <wfs:member>
          <app:restaurant gml:id="restaurant.{restaurant.id}">
            <app:id>{restaurant.id}</app:id>
            <app:name>Empty</app:name>
            <app:location />
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
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # Prove that the output is now rendered in EPSG:28992
        feature = xml_doc.find("wfs:member/app:restaurant", namespaces=NAMESPACES)
        geometry = feature.find("app:location/gml:Point", namespaces=NAMESPACES)
        assert geometry.attrib["srsName"] == "urn:ogc:def:crs:EPSG::28992"

        timestamp = xml_doc.attrib["timeStamp"]
        assert_xml_equal(
            response.content,
            f"""<wfs:FeatureCollection
       xmlns:app="http://example.org/gisserver"
       xmlns:gml="http://www.opengis.net/gml/3.2"
       xmlns:wfs="http://www.opengis.net/wfs/2.0"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
       timeStamp="{timestamp}" numberMatched="1" numberReturned="1">

        <wfs:member>
          <app:restaurant gml:id="restaurant.{restaurant.id}">
            <gml:boundedBy>
                 <gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992">
                <gml:lowerCorner>122411.00000717948 486250.0005178676</gml:lowerCorner>
                <gml:upperCorner>122411.00000717948 486250.0005178676</gml:upperCorner>
            </gml:Envelope>
            </gml:boundedBy>
            <app:id>{restaurant.id}</app:id>
            <app:name>Café Noir</app:name>
            <app:location>
              <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::28992">
                <gml:pos>122411.00000717948 486250.0005178676</gml:pos>
              </gml:Point>
            </app:location>
          </app:restaurant>
        </wfs:member>
    </wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_get_bbox(self, client, restaurant):
        """Prove that that parsing RESULTTYPE=hits works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&BBOX=122400,486200,122500,486300,urn:ogc:def:crs:EPSG::28992"
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(response.content, WFS_20_XSD)
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
        xml_doc = validate_xsd(response2.content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "0"
        assert xml_doc.attrib["numberReturned"] == "0"

    def test_get_hits(self, client, restaurant):
        """Prove that that parsing RESULTTYPE=hits works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&RESULTTYPE=hits"
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(response.content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "0"
        assert not xml_doc.getchildren()  # should not have children!
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            response.content,
            f"""<wfs:FeatureCollection
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   xmlns:wfs="http://www.opengis.net/wfs/2.0"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
   timeStamp="{timestamp}" numberMatched="1" numberReturned="0">
</wfs:FeatureCollection>""",  # noqa: E501
        )

    def test_get_geojson(self, client, restaurant):
        """Prove that the geojson export works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&outputformat=geojson"
        )
        assert response["content-type"] == "application/json; charset=utf-8"
        content = response.json()
        assert response.status_code == 200, content
        assert content == {
            "type": "FeatureCollection",
            "totalFeatures": 1,
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
                        "coordinates": [4.9087610129, 52.3631712637],
                    },
                    "properties": {"id": restaurant.id, "name": "Café Noir"},
                }
            ],
        }
