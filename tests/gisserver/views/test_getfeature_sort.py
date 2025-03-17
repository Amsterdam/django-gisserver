import pytest

from tests.gisserver.views.input import SORT_BY, SORT_BY_XML
from tests.requests import Get, Post, parametrize_response
from tests.utils import NAMESPACES, WFS_20_XSD, XML_NS, read_response, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeatureSort:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @parametrize_response(
        *(
            [
                Get(
                    "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                    f"&SORTBY={sort_by}",
                    id=name,
                    expect=expect,
                    url=url,
                )
                for (name, url, sort_by, expect) in SORT_BY
            ]
            + [
                Post(
                    f"""<GetFeature version="2.0.0" service="WFS" {XML_NS}>
                <Query typeNames="restaurant">
                    <fes:SortBy>
                        {sort_by}
                    </fes:SortBy>
                </Query>
                </GetFeature>
                """,
                    id=name,
                    expect=expect,
                    url=url,
                )
                for (name, url, sort_by, expect) in SORT_BY_XML
            ]
        )
    )
    def test_get_sort_by(self, restaurant, bad_restaurant, response):
        """Prove that that sorting with SORTBY=... works"""
        _assert_sort(response, response.expect)


def _assert_sort(response, expect):
    """Common logic for sort tests"""
    content = read_response(response)
    assert response["content-type"] == "text/xml; charset=utf-8", content
    assert response.status_code == 200, content
    assert "</wfs:FeatureCollection>" in content

    # Validate against the WFS 2.0 XSD
    xml_doc = validate_xsd(content, WFS_20_XSD)
    assert xml_doc.attrib["numberMatched"] == "2"
    assert xml_doc.attrib["numberReturned"] == "2"

    # Test sort ordering.
    restaurants = xml_doc.findall("wfs:member/app:restaurant", namespaces=NAMESPACES)
    names = [res.find("app:name", namespaces=NAMESPACES).text for res in restaurants]
    assert names == expect
