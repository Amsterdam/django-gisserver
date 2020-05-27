import json
import pytest
import sys
from urllib.parse import quote_plus
from xml.etree.ElementTree import QName

from gisserver.types import WGS84
from tests.constants import NAMESPACES
from tests.test_gisserver.models import Restaurant
from tests.utils import WFS_20_XSD, assert_xml_equal, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]

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
            <gml:Envelope srsName="urn:ogc:def:crs:EPSG::4326">
                <gml:lowerCorner>{POINT1_XML_WGS84}</gml:lowerCorner>
                <gml:upperCorner>{POINT1_XML_WGS84}</gml:upperCorner>
            </gml:Envelope>
        </gml:boundedBy>
        <app:location>
          <gml:Point gml:id="mini-restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
            <gml:pos>{POINT1_XML_WGS84}</gml:pos>
          </gml:Point>
        </app:location>
      </app:mini-restaurant>
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
        assert (
            message == "Invalid ID value: Field 'id' expected a number but got 'ABC'."
        )

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
