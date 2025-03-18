import pytest

from tests.utils import NAMESPACES, WFS_20_XSD, read_response, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

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
