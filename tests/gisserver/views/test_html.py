import pytest

from gisserver.parsers.xml import xmlns

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


class TestHTMLTemplates:
    """All tests for the ListStoredQueries method."""

    def test_get(self, client):
        """Prove that the happy flow works"""
        response = client.get("/v1/wfs/")
        assert response.status_code == 200
        assert response["content-type"] == "text/html; charset=utf-8"
        content = response.content.decode()

        assert "<h2>WFS Feature Types</h2>" in content
        assert "OUTPUTFORMAT=csv" in content
        assert "OUTPUTFORMAT=geojson" in content
        assert xmlns.xsd.value not in content
