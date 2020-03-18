import json
import sys
from urllib.parse import quote_plus

import pytest
from django.contrib.gis.gdal import SpatialReference
from django.urls import path
from lxml import etree

from gisserver.features import FeatureType, ServiceDescription
from gisserver.types import CRS, WGS84
from gisserver.views import WFSView
from tests.srid import RD_NEW_PROJ
from tests.test_gisserver.models import Restaurant
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

RD_NEW = CRS.from_string(
    "urn:ogc:def:crs:EPSG::28992", backend=SpatialReference(RD_NEW_PROJ),
)

# Despite efforts to sync the PROJ.4 definitions, there is still a minor difference
# between platforms, or library versions that cause coordinate shifts. Hopefully,
# no other changes are visible. Hence keeping these here for now. If there are more
# differences on other platforms, better perform a live transformation here to see
# what the expected values will be.
if sys.platform == "darwin":
    POINT1_XML_WGS84 = "4.908761012851219 52.363171263735715"
    POINT1_XML_RD = "122411.00000717948 486250.0005178676"
    POINT1_GEOJSON = [4.908761012851219, 52.363171263735715]  # GeoJSON is always WGS84
    POINT2_GEOJSON = [4.908903943932534, 52.36353134993197]  # GeoJSON is always WGS84
else:
    POINT1_XML_WGS84 = "4.90876101285122 52.36317126373569"
    POINT1_XML_RD = "122411.00000717954 486250.0005178673"
    POINT1_GEOJSON = [4.90876101285122, 52.36317126373569]
    POINT2_GEOJSON = [4.908903943932534, 52.36353134993195]


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
            Restaurant.objects.all(),
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
          <Format>text/xml; subtype=gml/3.2</Format>
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
        assert field_names == ["id", "name", "city_id", "location", "rating", "created"]

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
          <element name="id" type="integer" minOccurs="0" />
          <element name="name" type="string" minOccurs="0" />
          <element name="city_id" type="integer" minOccurs="0" />
          <element name="location" type="gml:GeometryPropertyType" minOccurs="0" maxOccurs="1"/>
          <element name="rating" type="double" minOccurs="0" />
          <element name="created" type="date" minOccurs="0" />
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

    @staticmethod
    def read_response(response) -> str:
        # works for all HttpResponse subclasses.
        return b"".join(response).decode()

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
        content = self.read_response(response)
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
        <gml:boundedBy>
            <gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">
                <gml:lowerCorner>{POINT1_XML_WGS84}</gml:lowerCorner>
                <gml:upperCorner>{POINT1_XML_WGS84}</gml:upperCorner>
            </gml:Envelope>
        </gml:boundedBy>
        <app:id>{restaurant.id}</app:id>
        <app:name>Café Noir</app:name>
        <app:city_id>{restaurant.city_id}</app:city_id>
        <app:location>
          <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos>{POINT1_XML_WGS84}</gml:pos>
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
        content = self.read_response(response)
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

    def test_get_srs_name(self, client, restaurant):
        """Prove that specifying SRSNAME works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&SRSNAME=urn:ogc:def:crs:EPSG::28992"
        )
        content = self.read_response(response)
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
            <gml:boundedBy>
              <gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992">
                <gml:lowerCorner>{POINT1_XML_RD}</gml:lowerCorner>
                <gml:upperCorner>{POINT1_XML_RD}</gml:upperCorner>
              </gml:Envelope>
            </gml:boundedBy>
            <app:id>{restaurant.id}</app:id>
            <app:name>Café Noir</app:name>
            <app:city_id>{restaurant.city_id}</app:city_id>
            <app:location>
              <gml:Point gml:id="restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::28992">
                <gml:pos>{POINT1_XML_RD}</gml:pos>
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
        content = self.read_response(response)
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
        content2 = self.read_response(response2)
        xml_doc = validate_xsd(content2, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "0"
        assert xml_doc.attrib["numberReturned"] == "0"

    FILTERS = {
        "simple": """
            <?xml version="1.0"?>
            <fes:Filter
                 xmlns:fes="http://www.opengis.net/fes/2.0"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xsi:schemaLocation="http://www.opengis.net/fes/2.0
                 http://schemas.opengis.net/filter/2.0/filterAll.xsd">
                <fes:PropertyIsGreaterThanOrEqualTo>
                    <fes:ValueReference>rating</fes:ValueReference>
                    <fes:Literal>3.0</fes:Literal>
                </fes:PropertyIsGreaterThanOrEqualTo>
            </fes:Filter>""",
        "like": """
            <?xml version="1.0"?>
            <fes:Filter
                 xmlns:fes="http://www.opengis.net/fes/2.0"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xsi:schemaLocation="http://www.opengis.net/fes/2.0
                 http://schemas.opengis.net/filter/2.0/filterAll.xsd">
                <fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!">
                    <fes:ValueReference>name</fes:ValueReference>
                    <fes:Literal>C?fé*</fes:Literal>
                </fes:PropertyIsLike>
            </fes:Filter>""",
        "bbox": """
            <?xml version="1.0"?>
            <fes:Filter
                xmlns:fes="http://www.opengis.net/fes/2.0"
                xmlns:gml="http://www.opengis.net/gml/3.2"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xsi:schemaLocation="http://www.opengis.net/fes/2.0
                http://schemas.opengis.net/filter/2.0/filterAll.xsd
                http://www.opengis.net/gml/3.2
                http://schemas.opengis.net/gml/3.2.1/gml.xsd">
                <fes:BBOX>
                    <fes:ValueReference>location</fes:ValueReference>
                    <gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992">
                        <gml:lowerCorner>122410 486240</gml:lowerCorner>
                        <gml:upperCorner>122412 486260</gml:upperCorner>
                    </gml:Envelope>
                </fes:BBOX>
            </fes:Filter>""",
        "and": """
        <?xml version="1.0"?>
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:gml="http://www.opengis.net/gml/3.2"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd
            http://www.opengis.net/gml/3.2
            http://schemas.opengis.net/gml/3.2.1/gml.xsd">
            <fes:And>
                <fes:PropertyIsGreaterThanOrEqualTo>
                    <fes:ValueReference>rating</fes:ValueReference>
                    <fes:Literal>3.0</fes:Literal>
                </fes:PropertyIsGreaterThanOrEqualTo>
                <fes:BBOX>
                    <fes:ValueReference>location</fes:ValueReference>
                    <gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992">
                        <gml:lowerCorner>122410 486240</gml:lowerCorner>
                        <gml:upperCorner>122412 486260</gml:upperCorner>
                    </gml:Envelope>
                </fes:BBOX>
            </fes:And>
        </fes:Filter>""",
    }

    @pytest.mark.parametrize("filter_name", list(FILTERS.keys()))
    def test_get_filter(self, client, restaurant, bad_restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter = self.FILTERS[filter_name].strip()

        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&FILTER=" + quote_plus(filter)
        )
        content = self.read_response(response)
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

    INVALID_FILTERS = {
        "syntax": (
            """<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">FDFDS</fes:Filter""",
            "Unable to parse FILTER argument: unclosed token: line 1, column 60",
        ),
        "missing_xmlns": (
            """<?xml version="1.0"?>
            <fes:Filter
                 xmlns:fes="http://www.opengis.net/fes/2.0"
                 xsi:schemaLocation="http://www.opengis.net/fes/2.0
                 http://schemas.opengis.net/filter/2.0/filterAll.xsd">
                <fes:PropertyIsGreaterThanOrEqualTo>
                    <fes:ValueReference>rating</fes:ValueReference>
                    <fes:Literal>3.0</fes:Literal>
                </fes:PropertyIsGreaterThanOrEqualTo>
            </fes:Filter>""",
            "Unable to parse FILTER argument: unbound prefix: line 2, column 12",
        ),
        "closing_tag": (
            """
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsGreaterThanOrEqualTo>
                <fes:ValueReference>rating</fes:ValueReference>
                <fes:Literal>3.0</fes:Literal>
            </fes:PropertyIsGreaterThanOrEqualTofoo>
        </fes:Filter>""",
            "Unable to parse FILTER argument: mismatched tag: line 9, column 14",
        ),
        "float_text": (
            """
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsGreaterThanOrEqualTo>
                <fes:ValueReference>rating</fes:ValueReference>
                <fes:Literal>TEXT</fes:Literal>
            </fes:PropertyIsGreaterThanOrEqualTo>
        </fes:Filter>""",
            "Invalid filter query: Field 'rating' expected a number but got 'TEXT'.",
        ),
    }

    @pytest.mark.parametrize("filter_name", list(INVALID_FILTERS.keys()))
    def test_get_filter_invalid(self, client, restaurant, filter_name):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        filter, expect_msg = self.INVALID_FILTERS[filter_name]

        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&FILTER=" + quote_plus(filter.strip())
        )
        content = self.read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "InvalidParameterValue"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == expect_msg

    def test_get_hits(self, client, restaurant):
        """Prove that that parsing RESULTTYPE=hits works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&RESULTTYPE=hits"
        )
        content = self.read_response(response)
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

    SORT_BY = {
        "name": ("name", ["Café Noir", "Foo Bar"]),
        "name-asc": ("name ASC", ["Café Noir", "Foo Bar"]),
        "name-desc": ("name DESC", ["Foo Bar", "Café Noir"]),
        "rating-desc": ("rating DESC", ["Café Noir", "Foo Bar"]),
        "rating,name-asc": ("rating,name ASC", ["Foo Bar", "Café Noir"]),
    }

    @pytest.mark.parametrize("ordering", list(SORT_BY.keys()))
    def test_get_sort_by(self, client, restaurant, bad_restaurant, ordering):
        """Prove that that parsing BBOX=... works"""
        sort_by, expect = self.SORT_BY[ordering]
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            f"&SORTBY={sort_by}"
        )
        content = self.read_response(response)
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

    def test_get_geojson(self, client, restaurant, bad_restaurant):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&outputformat=geojson"
        )
        assert response["content-type"] == "application/json; charset=utf-8"
        content = self.read_response(response)
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
        content = self.read_response(response)

        # If the response is invalid json, there was likely
        # some exception that aborted further writing.
        data = self.read_json(content)

        assert len(data["features"]) == 1000
        assert data["numberReturned"] == 1000
        assert data["numberMatched"] == 1500
