import pytest

from tests.requests import Get, Post, parametrize_response
from tests.utils import XML_NS, assert_ows_exception

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeature:
    """Basic tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=denied-feature"),
        Post(
            f"""
                <GetFeature version="2.0.0" service="WFS" {XML_NS}>
                <Query typeNames="denied-feature"></Query>
                </GetFeature>
                """
        ),
    )
    def test_get_unauth(self, response):
        """Prove that features may block access.
        Note that HTTP 403 is not in the WFS 2.0 spec, but still useful to have.
        """
        assert_ows_exception(
            response, "PermissionDenied", "No access to this feature.", expect_status=403
        )

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=1.1.0",
        ),
        Post(
            '<GetFeature xmlns="http://www.opengis.net/wfs" service="WFS" version="1.1.0" outputFormat="GML3"'
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            ' xsi:schemaLocation="http://www.opengis.net/wfs http://schemas.opengis.net/wfs/1.1.0/wfs.xsd">'
            '  <Query typeName="ows:wijk" srsName="EPSG:28992">'
            '    <Filter xmlns="http://www.opengis.net/ogc">'
            "      <Intersects>"
            "        <PropertyName>msGeometry</PropertyName>"
            '        <Polygon xmlns="http://www.opengis.net/gml">'
            '          <exterior><LinearRing><posList srsDimension="2">'
            "              118367.24520866408 486459.47576786246 118367.24520866408 485534.2345172382"
            "              119634.45393402915 485534.2345172382 119634.45393402915 486459.47576786246"
            "              118367.24520866408 486459.47576786246"
            "          </posList></LinearRing></exterior>"
            "        </Polygon>"
            "      </Intersects>"
            "    </Filter>"
            "  </Query>"
            "</GetFeature>",
            validate_xml=False,
        ),
    )
    def test_get_invalid_version(self, response):
        """Prove that version negotiation works"""
        assert_ows_exception(
            response, "InvalidParameterValue", "This server does not support WFS version 1.1.0."
        )
