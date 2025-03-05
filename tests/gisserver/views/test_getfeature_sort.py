import pytest

from tests.constants import NAMESPACES, XML_NS
from tests.gisserver.views.input import (
    SORT_BY,
    SORT_BY_COMPLEX,
    SORT_BY_COMPLEX_XML,
    SORT_BY_FLATTENED,
    SORT_BY_FLATTENED_XML,
    SORT_BY_XML,
)
from tests.utils import WFS_20_XSD, read_response, validate_xsd

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeatureSort:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @pytest.mark.parametrize("ordering", list(SORT_BY.keys()))
    def test_get_sort_by(self, client, restaurant, bad_restaurant, ordering):
        """Prove that that sorting with SORTBY=... works"""
        sort_by, expect = SORT_BY[ordering]
        response = client.get(
            "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            f"&SORTBY={sort_by}"
        )
        _assert_sort(response, expect)

    @pytest.mark.parametrize("ordering", list(SORT_BY_COMPLEX.keys()))
    def test_get_sort_by_complex(self, client, restaurant, bad_restaurant, ordering):
        """Prove that sorting on XPath works for complex types"""
        sort_by, expect = SORT_BY_COMPLEX[ordering]
        response = client.get(
            "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&TYPENAMES=restaurant&SORTBY={sort_by}"
        )
        _assert_sort(response, expect)

    @pytest.mark.parametrize("ordering", list(SORT_BY_FLATTENED.keys()))
    def test_get_sort_by_flattened(self, client, restaurant, bad_restaurant, ordering):
        """Prove that sorting on XPath works for flattened types"""
        sort_by, expect = SORT_BY_FLATTENED[ordering]
        response = client.get(
            "/v1/wfs-flattened/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            f"&TYPENAMES=restaurant&SORTBY={sort_by}"
        )
        _assert_sort(response, expect)


@pytest.mark.django_db
class TestGetFeatureSortWithPostRequest:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @pytest.mark.parametrize("ordering", list(SORT_BY_XML.keys()))
    def test_get_sort_by(self, client, restaurant, bad_restaurant, ordering):
        """Prove that that sorting with SORTBY=... works"""
        sort_by, order, expect = SORT_BY_XML[ordering]
        xml = f"""<GetFeature version="2.0.0" service="WFS" {XML_NS}>
                <Query typeNames="restaurant">
                    <fes:SortBy>
                        <fes:SortProperty>
                            <fes:ValueReference>{sort_by}</fes:ValueReference>
                            {f"<fes:SortOrder>{order}</fes:SortOrder>" if order else ""}
                        </fes:SortProperty>
                    </fes:SortBy>
                </Query>
                </GetFeature>
                """

        response = client.post("/v1/wfs/", data=xml, content_type="application/xml")
        _assert_sort(response, expect)

    @pytest.mark.parametrize("ordering", list(SORT_BY_COMPLEX_XML.keys()))
    def test_get_sort_by_complex(self, client, restaurant, bad_restaurant, ordering):
        """Prove that sorting on XPath works for complex types"""
        sort_by, order, expect = SORT_BY_COMPLEX_XML[ordering]
        xml = f"""<GetFeature version="2.0.0" service="WFS" {XML_NS}>
                <Query typeNames="restaurant">
                    <fes:SortBy>
                        <fes:SortProperty>
                            <fes:ValueReference>{sort_by}</fes:ValueReference>
                            {f"<fes:SortOrder>{order}</fes:SortOrder>" if order else ""}
                        </fes:SortProperty>
                    </fes:SortBy>
                </Query>
                </GetFeature>
                """
        response = client.post("/v1/wfs-complextypes/", data=xml, content_type="application/xml")
        _assert_sort(response, expect)

    @pytest.mark.parametrize("ordering", list(SORT_BY_FLATTENED_XML.keys()))
    def test_get_sort_by_flattened(self, client, restaurant, bad_restaurant, ordering):
        """Prove that sorting on XPath works for flattened types"""
        sort_by, order, expect = SORT_BY_FLATTENED_XML[ordering]
        xml = f"""<GetFeature version="2.0.0" service="WFS" {XML_NS}>
                <Query typeNames="restaurant">
                    <fes:SortBy>
                        <fes:SortProperty>
                            <fes:ValueReference>{sort_by}</fes:ValueReference>
                            {f"<fes:SortOrder>{order}</fes:SortOrder>" if order else ""}
                        </fes:SortProperty>
                    </fes:SortBy>
                </Query>
                </GetFeature>
                """
        response = client.post("/v1/wfs-flattened/", data=xml, content_type="application/xml")
        _assert_sort(response, expect)


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
