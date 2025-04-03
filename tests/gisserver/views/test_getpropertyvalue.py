from urllib.parse import quote_plus

import pytest

from tests.gisserver.views.input import (
    FILTERS,
    INVALID_FILTERS,
    SORT_BY,
    SORT_BY_XML,
)
from tests.requests import Get, Post, parametrize_response
from tests.utils import (
    NAMESPACES,
    WFS_20_XSD,
    XML_NS,
    assert_xml_equal,
    clean_filter_for_xml,
    read_response,
    validate_xsd,
)

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]
gml32 = quote_plus("application/gml+xml; version=3.2")


@pytest.mark.django_db
class TestGetPropertyValue:
    """All tests for the GetPropertyValue method."""

    XPATHS = ["name", "app:name", "app:restaurant/app:name", "/restaurant/name"]

    @parametrize_response(
        *(
            [
                Get(
                    f"?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
                    f"&VALUEREFERENCE={xpath}&OUTPUTFORMAT={gml32}"
                )
                for xpath in XPATHS
            ]
            + [
                Post(
                    f"""<GetPropertyValue version="2.0.0" service="WFS" outputFormat="application/gml+xml; version=3.2" valueReference="{xpath}" {XML_NS}>
                <Query typeNames="restaurant">
                </Query>
                </GetPropertyValue>
                """
                )
                for xpath in XPATHS
            ]
        )
    )
    def test_get(self, restaurant, bad_restaurant, response):
        """Prove that the happy flow works"""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:ValueCollection
                    xmlns:app="http://example.org/gisserver"
                    xmlns:gml="http://www.opengis.net/gml/3.2"
                    xmlns:wfs="http://www.opengis.net/wfs/2.0"
                    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                    xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
                    timeStamp="{timestamp}" numberMatched="2" numberReturned="2">
                <wfs:member>
                    <app:name>Café Noir</app:name>
                </wfs:member>
                <wfs:member>
                    <app:name>Foo Bar</app:name>
                </wfs:member>
                </wfs:ValueCollection>""",  # noqa: E501
        )

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&VALUEREFERENCE=location"
        ),
        Post(
            f"""<GetPropertyValue version="2.0.0" service="WFS" valueReference="location" {XML_NS}>
                <Query typeNames="restaurant">
                </Query>
                </GetPropertyValue>
                """
        ),
    )
    def test_get_location(self, restaurant, coordinates, response):
        """Prove that rendering geometry values also works"""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:ValueCollection
                xmlns:app="http://example.org/gisserver"
                xmlns:gml="http://www.opengis.net/gml/3.2"
                xmlns:wfs="http://www.opengis.net/wfs/2.0"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
                timeStamp="{timestamp}" numberMatched="1" numberReturned="1">
            <wfs:member>
                <app:location>
                <gml:Point gml:id="Restaurant.{restaurant.id}.1" srsName="urn:ogc:def:crs:EPSG::4326">
                    <gml:pos srsDimension="2">{coordinates.point1_xml_wgs84}</gml:pos>
                </gml:Point>
                </app:location>
            </wfs:member>
            </wfs:ValueCollection>""",  # noqa: E501
        )

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&VALUEREFERENCE=location"
        ),
        Post(
            f"""<GetPropertyValue version="2.0.0" service="WFS" valueReference="location" {XML_NS}>
                <Query typeNames="restaurant">
                </Query>
                </GetPropertyValue>
                """
        ),
    )
    def test_get_location_null(self, empty_restaurant, response):
        """Prove that the empty geometry values don't crash the rendering."""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"
        timestamp = xml_doc.attrib["timeStamp"]

        # TODO: should this return an <wfs:member xsi:nil="true" /> instead?
        assert_xml_equal(
            content,
            f"""<wfs:ValueCollection
                xmlns:app="http://example.org/gisserver"
                xmlns:gml="http://www.opengis.net/gml/3.2"
                xmlns:wfs="http://www.opengis.net/wfs/2.0"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
                timeStamp="{timestamp}" numberMatched="1" numberReturned="1">
            <wfs:member>
                <app:location xsi:nil="true"/>
            </wfs:member>
            </wfs:ValueCollection>""",  # noqa: E501
        )

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&VALUEREFERENCE=tags"
        ),
        Post(
            f"""<GetPropertyValue version="2.0.0" service="WFS" valueReference="tags" {XML_NS}>
                <Query typeNames="restaurant">
                </Query>
                </GetPropertyValue>
                """
        ),
    )
    def test_get_tags_array(self, restaurant, response):
        """Prove that the rendering an array field produces some WFS-compatible response."""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:ValueCollection
                xmlns:app="http://example.org/gisserver"
                xmlns:gml="http://www.opengis.net/gml/3.2"
                xmlns:wfs="http://www.opengis.net/wfs/2.0"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
                timeStamp="{timestamp}" numberMatched="1" numberReturned="1">
            <wfs:member><app:tags>cafe</app:tags></wfs:member>
            <wfs:member><app:tags>black</app:tags></wfs:member>
            </wfs:ValueCollection>""",  # noqa: E501
        )

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&VALUEREFERENCE=@gml:id"
        ),
        Post(
            f"""<GetPropertyValue version="2.0.0" service="WFS" valueReference="@gml:id" {XML_NS}>
                <Query typeNames="restaurant">
                </Query>
                </GetPropertyValue>
                """
        ),
    )
    def test_get_attribute(self, restaurant, bad_restaurant, response):
        """Prove that referencing attributes works"""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:ValueCollection
                xmlns:app="http://example.org/gisserver"
                xmlns:gml="http://www.opengis.net/gml/3.2"
                xmlns:wfs="http://www.opengis.net/wfs/2.0"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
                timeStamp="{timestamp}" numberMatched="2" numberReturned="2">
            <wfs:member>restaurant.{restaurant.pk}</wfs:member>
            <wfs:member>restaurant.{bad_restaurant.pk}</wfs:member>
            </wfs:ValueCollection>""",  # noqa: E501
        )

    @parametrize_response(
        *(
            [
                Get(
                    "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
                    "&VALUEREFERENCE=name&FILTER=" + quote_plus(filter.strip()),
                    id=name,
                    url=url,
                )
                for (name, url, filter) in FILTERS
            ]
            + [
                Post(
                    f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name" {XML_NS}>
            <Query typeNames="restaurant">
            {clean_filter_for_xml(filter).strip()}
            </Query>
            </GetPropertyValue>
            """,
                    id=name,
                    url=url,
                )
                for (name, url, filter) in FILTERS
            ]
        )
    )
    def test_get_filter(self, client, restaurant, restaurant_m2m, bad_restaurant, response):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        _assert_filter(response)

    @parametrize_response(
        *(
            [
                Get(
                    "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
                    "&VALUEREFERENCE=name&FILTER=" + quote_plus(filter.strip()),
                    expect=expect,
                    id=name,
                )
                for name, (filter, expect, _) in INVALID_FILTERS.items()
            ]
            + [
                Post(
                    f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name" {XML_NS}>
                <Query typeNames="restaurant">
                {clean_filter_for_xml(filter).strip()}
                </Query>
                </GetPropertyValue>
                """,
                    expect=expect,
                    id=name,
                )
                for name, (filter, _, expect) in INVALID_FILTERS.items()
            ]
        )
    )
    def test_get_filter_invalid(self, restaurant, response):
        """Prove that that parsing FILTER=<fes:Filter>... works"""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content
        assert "</ows:Exception>" in content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        message = exception.find("ows:ExceptionText", NAMESPACES).text

        assert exception.attrib["exceptionCode"] == response.expect.code, message
        assert message.startswith(response.expect.text)

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=denied-feature"
            "&VALUEREFERENCE=name"
        ),
        Post(
            f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name" {XML_NS}>
            <Query typeNames="denied-feature">
            </Query>
            </GetPropertyValue>
            """
        ),
    )
    def test_get_unauth(self, response):
        """Prove that features may block access.
        Note that HTTP 403 is not in the WFS 2.0 spec, but still useful to have.
        """
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

    @parametrize_response(
        Get(
            lambda start_index: "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            f"&VALUEREFERENCE=name&SORTBY=name&COUNT=1&STARTINDEX={start_index}",
        ),
        Post(
            lambda start_index: f"""<GetPropertyValue version="2.0.0" service="WFS" count="1" startIndex="{start_index}" valueReference="name" {XML_NS}>
                <Query typeNames="restaurant">
                    <fes:SortBy>
                        <fes:SortProperty>
                            <fes:ValueReference>name</fes:ValueReference>
                            <fes:SortOrder>ASC</fes:SortOrder>
                        </fes:SortProperty>
                    </fes:SortBy>
                </Query>
                </GetPropertyValue>
                """,
        ),
    )
    def test_pagination(self, client, restaurant, bad_restaurant, response):
        """Prove that that parsing BBOX=... works"""
        names = []
        for start_index in range(4):  # test whether last page stops
            res = response(start_index)
            content = read_response(res)
            assert res["content-type"] == "text/xml; charset=utf-8", content
            assert res.status_code == 200, content
            assert "</wfs:ValueCollection>" in content

            # Validate against the WFS 2.0 XSD
            xml_doc = validate_xsd(content, WFS_20_XSD)
            assert xml_doc.attrib["numberMatched"] == "2"
            assert xml_doc.attrib["numberReturned"] == "1"

            # Collect the names
            members = xml_doc.findall("wfs:member", namespaces=NAMESPACES)
            names.extend(res.find("app:name", namespaces=NAMESPACES).text for res in members)
            url = xml_doc.attrib.get("next")
            if not url:
                break

        # Prove that both items were returned
        assert len(names) == 2
        assert names[0] != names[1]

    @parametrize_response(
        *(
            [
                Get(
                    "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
                    f"&VALUEREFERENCE=name&SORTBY={sort_by}",
                    id=name,
                    expect=expect,
                    url=url,
                )
                for (name, url, sort_by, expect) in SORT_BY
            ]
            + [
                Post(
                    f"""<GetPropertyValue version="2.0.0" service="WFS" valueReference="name" {XML_NS}>
                <Query typeNames="restaurant">
                    <fes:SortBy>
                        {sort_by}
                    </fes:SortBy>
                </Query>
                </GetPropertyValue>
                """,
                    id=name,
                    expect=expect,
                    url=url,
                )
                for (name, url, sort_by, expect) in SORT_BY_XML
            ]
        )
    )
    def test_get_sort_by(self, client, restaurant, bad_restaurant, response):
        """Prove that that parsing BBOX=... works"""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"

        # Test sort ordering.
        members = xml_doc.findall("wfs:member", namespaces=NAMESPACES)
        names = [res.find("app:name", namespaces=NAMESPACES).text for res in members]
        assert names == response.expect

    @parametrize_response(
        Get(
            lambda id: "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            f"&RESOURCEID=restaurant.{id}&VALUEREFERENCE=name",
        ),
        Post(
            lambda id: f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name"
                resourceId="restaurant.{id}" {XML_NS}>
                </GetPropertyValue>
                """,
        ),
    )
    def test_resource_id(self, restaurant, bad_restaurant, response):
        """Prove that fetching objects by ID works."""
        res = response(restaurant.id)
        content = read_response(res)
        assert res["content-type"] == "text/xml; charset=utf-8", content
        assert res.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "1"
        assert xml_doc.attrib["numberReturned"] == "1"

        # Test sort ordering.
        members = xml_doc.findall("wfs:member", namespaces=NAMESPACES)
        names = [res.find("app:name", namespaces=NAMESPACES).text for res in members]
        assert names == ["Café Noir"]

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0&TYPENAMES=restaurant"
            "&RESOURCEID=restaurant.0&VALUEREFERENCE=name"
        ),
        Post(
            f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name" resourceId="restaurant.0" {XML_NS}>
                <Query typeNames="restaurant"></Query>
                </GetPropertyValue>
                """
        ),
    )
    def test_resource_id_unknown_id(self, restaurant, bad_restaurant, response):
        """Prove that unknown IDs simply return an empty list."""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 200, content
        assert "</wfs:ValueCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "0"
        assert xml_doc.attrib["numberReturned"] == "0"

        # Test sort ordering.
        members = xml_doc.findall("wfs:member", namespaces=NAMESPACES)
        assert len(members) == 0

    @parametrize_response(
        Get(
            lambda id: "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            "&TYPENAMES=mini-restaurant"
            f"&RESOURCEID=restaurant.{id}&VALUEREFERENCE=location",
        ),
        Post(
            lambda id: f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="location" resourceId="restaurant.{id}" {XML_NS}>
                <Query typeNames="mini-restaurant"></Query>
                </GetPropertyValue>
                """,
        ),
    )
    def test_resource_id_typename_mismatch(self, restaurant, bad_restaurant, response):
        """Prove that TYPENAMES should be omitted, or match the RESOURCEID."""
        res = response(restaurant.id)
        content = read_response(res)
        assert res["content-type"] == "text/xml; charset=utf-8", content
        assert res.status_code == 400, content
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

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            "&RESOURCEID=restaurant.ABC&VALUEREFERENCE=name"
        ),
        Post(
            f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name" resourceId="restaurant.ABC" {XML_NS}>
                </GetPropertyValue>
                """
        ),
    )
    def test_resource_id_invalid(self, restaurant, bad_restaurant, response):
        """Prove that TYPENAMES should be omitted, or match the RESOURCEID."""
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

    @parametrize_response(
        Get(
            lambda id: "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            f"&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            f"&ID=restaurant.{id}&VALUEREFERENCE=name"
        ),
        Post(
            lambda id: f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name"
                storedQueryId="urn:ogc:def:query:OGC-WFS::GetFeatureById" id="restaurant.{id}" {XML_NS}>
                </GetPropertyValue>
            """,
        ),
    )
    def test_get_feature_by_id_stored_query(self, restaurant, bad_restaurant, response):
        """Prove that fetching objects by ID works."""
        res = response(restaurant.id)
        content = read_response(res)
        assert res["content-type"] == "text/xml; charset=utf-8", content
        assert res.status_code == 200, content
        assert "</app:restaurant>" not in content
        assert "</wfs:FeatureCollection>" not in content

        # See whether our feature is rendered
        # For GetFeatureById, no <wfs:FeatureCollection> is returned.
        assert_xml_equal(
            content,
            """<app:name xmlns:app="http://example.org/gisserver"
                xmlns:gml="http://www.opengis.net/gml/3.2">Café Noir</app:name>""",
        )

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            "&ID=restaurant.ABC&VALUEREFERENCE=name"
        ),
        Post(
            f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name"
                storedQueryId="urn:ogc:def:query:OGC-WFS::GetFeatureById" id="restaurant.ABC" {XML_NS}>
                </GetPropertyValue>"""
        ),
    )
    def test_get_feature_by_id_bad_id(self, restaurant, bad_restaurant, response):
        """Prove that invalid IDs are properly handled."""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 400, content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "InvalidParameterValue"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == "Invalid ID value: Field 'id' expected a number but got 'ABC'."

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetPropertyValue&VERSION=2.0.0"
            "&STOREDQUERY_ID=urn:ogc:def:query:OGC-WFS::GetFeatureById"
            "&ID=restaurant.0&VALUEREFERENCE=name"
        ),
        Post(
            f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name"
                storedQueryId="urn:ogc:def:query:OGC-WFS::GetFeatureById" id="restaurant.0" {XML_NS}>
                </GetPropertyValue>
            """
        ),
    )
    def test_get_feature_by_id_404(self, restaurant, bad_restaurant, response):
        """Prove that missing IDs are properly handled."""
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 404, content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "NotFound"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == "Feature not found with ID 0."


@pytest.mark.django_db
class TestGetPropertyValueWithPostRequest:
    """All tests for the GetPropertyValue method."""

    def test_get_feature_by_id_404(self, client, restaurant, bad_restaurant):
        """Prove that missing IDs are properly handled."""
        xml = f"""<GetPropertyValue service="WFS" version="2.0.0" valueReference="name"
        storedQueryId="urn:ogc:def:query:OGC-WFS::GetFeatureById" id="restaurant.0"
        {XML_NS}>
        </GetPropertyValue>
            """
        response = client.post("/v1/wfs/", data=xml, content_type="application/xml")
        content = read_response(response)
        assert response["content-type"] == "text/xml; charset=utf-8", content
        assert response.status_code == 404, content

        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["version"] == "2.0.0"
        exception = xml_doc.find("ows:Exception", NAMESPACES)
        assert exception.attrib["exceptionCode"] == "NotFound"

        message = exception.find("ows:ExceptionText", NAMESPACES).text
        assert message == "Feature not found with ID 0."


def _assert_filter(response, expect="Café Noir"):
    content = read_response(response)
    assert response["content-type"] == "text/xml; charset=utf-8", content
    assert response.status_code == 200, content
    assert "</wfs:ValueCollection>" in content

    # Validate against the WFS 2.0 XSD
    xml_doc = validate_xsd(content, WFS_20_XSD)
    assert xml_doc.attrib["numberMatched"] == "1"
    assert xml_doc.attrib["numberReturned"] == "1"

    # Assert that the correct object was matched
    name = xml_doc.find("wfs:member/app:name", namespaces=NAMESPACES).text
    assert name == expect
