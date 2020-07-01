import pytest

from tests.utils import WFS_20_XSD, assert_xml_equal, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


class TestDescribeStoredQueries:
    """All tests for the DescribeStoredQueries method."""

    def test_get(self, client):
        """Prove that the happy flow works"""
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=DescribeStoredQueries&VERSION=2.0.0"
        )
        content = response.content.decode()
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "DescribeStoredQueriesResponse" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert len(xml_doc) == 1

        assert_xml_equal(
            content,
            """<wfs:DescribeStoredQueriesResponse
    xmlns="http://www.opengis.net/wfs/2.0"
    xmlns:app="http://example.org/gisserver"
    xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd">
  <StoredQueryDescription id="urn:ogc:def:query:OGC-WFS::GetFeatureById">
    <Title>Get feature by identifier</Title>
    <Abstract>Returns the single feature that corresponds with the ID argument</Abstract>
    <Parameter name="ID" type="xs:string"/>
    <QueryExpressionText isPrivate="true" language="urn:ogc:def:queryLanguage:OGC-WFS::WFS_QueryExpression" returnFeatureTypes="restaurant mini-restaurant denied-feature"/>
  </StoredQueryDescription>
</wfs:DescribeStoredQueriesResponse>""",  # noqa: E501
        )
