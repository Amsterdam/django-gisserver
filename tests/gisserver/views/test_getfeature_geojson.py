import django
import pytest

from gisserver import conf
from tests.requests import Get, Post, Url, parametrize_response
from tests.utils import XML_NS, read_json, read_response

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeatureGeoJson:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&outputformat=geojson"
        ),
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&outputformat=application/json; subtype=geojson; charset=utf-8"
        ),
        Post(
            f"""
                <GetFeature version="2.0.0" outputFormat="geojson" service="WFS" {XML_NS}>
                <Query typeNames="restaurant"></Query>
                </GetFeature>
                """
        ),
    )
    def test_get_geojson(
        self, restaurant, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(2):
            assert response["content-type"] == "application/geo+json; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        data = read_json(content)

        assert data["features"][0]["geometry"]["coordinates"] == coordinates.point1_geojson
        assert data == {
            "type": "FeatureCollection",
            "links": [],
            "timeStamp": data["timeStamp"],
            "numberMatched": 2,
            "numberReturned": 2,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"},
            },
            "features": [
                {
                    "type": "Feature",
                    "id": f"restaurant.{restaurant.id}",
                    "geometry_name": "Café Noir",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point1_geojson,
                    },
                    "properties": {
                        "id": restaurant.id,
                        "name": "Café Noir",
                        "city_id": restaurant.city_id,
                        "rating": 5.0,
                        "is_open": True,
                        "created": "2020-04-05T12:11:10+00:00",
                        "tags": ["cafe", "black"],
                    },
                },
                {
                    "type": "Feature",
                    "id": f"restaurant.{bad_restaurant.id}",
                    "geometry_name": "Foo Bar",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point2_geojson,
                    },
                    "properties": {
                        "id": bad_restaurant.id,
                        "name": "Foo Bar",
                        "city_id": None,
                        "rating": 1.0,
                        "is_open": False,
                        "created": "2020-04-05T20:11:10+00:00",
                        "tags": None,
                    },
                },
            ],
        }

    @pytest.mark.skipif(
        django.VERSION < (5, 0), reason="GeneratedField is only available in Django >= 5"
    )
    def test_get_geojson_generated_field(
        self,
        client,
        generated_field,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(2):
            response = client.get(
                "/v1/wfs-gen-field/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=modelwithgeneratedfields"
                "&outputformat=geojson"
            )
            assert response["content-type"] == "application/geo+json; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        data = read_json(content)

        assert data == {
            "type": "FeatureCollection",
            "links": [],
            "timeStamp": data["timeStamp"],
            "numberMatched": 1,
            "numberReturned": 1,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"},
            },
            "features": [
                {
                    "type": "Feature",
                    "id": f"modelwithgeneratedfields.{generated_field.id}",
                    "geometry_name": "Palindrome",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.translated_geojson,
                    },
                    "properties": {
                        "id": generated_field.id,
                        "name": "Palindrome",
                        "name_reversed": "emordnilaP",
                    },
                },
            ],
        }

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&vendor-arg=foobar&outputformat=geojson&COUNT=1000",
            expect=(
                "http://testserver/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&vendor-arg=foobar&outputformat=geojson&COUNT=1000&STARTINDEX=1000"
            ),
        ),
        Post(
            f"""
                <GetFeature version="2.0.0" outputFormat="geojson" count="1000" service="WFS" {XML_NS}>
                <Query typeNames="restaurant"></Query>
                </GetFeature>
                """,
            query="?vendor-arg=foobar",
            expect=(
                "http://testserver/v1/wfs/?vendor-arg=foobar"
                "&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
                "&TYPENAMES=restaurant&OUTPUTFORMAT=geojson&COUNT=1000&STARTINDEX=1000"
            ),
        ),
    )
    @pytest.mark.parametrize("use_count", [1, 0])
    def test_get_geojson_pagination(
        self, use_count, monkeypatch, many_restaurants, django_assert_max_num_queries, response
    ):
        """Prove that the geojson export handles pagination.

        Two variations are tested; when normal COUNT happens,
        or a sentinel object is used to detect there are more results.
        """
        monkeypatch.setattr(conf, "GISSERVER_COUNT_NUMBER_MATCHED", use_count)

        with django_assert_max_num_queries(1 + use_count):
            # before stream starts
            assert response["content-type"] == "application/geo+json; charset=utf-8"
            content = read_response(response)

        # If the response is invalid json, there was likely
        # some exception that aborted further writing.
        data = read_json(content)

        assert len(data["features"]) == 1000
        assert data["numberReturned"] == 1000
        assert data["numberMatched"] == (1500 if use_count else None)

        # Check that the generates links are as expected, and don't mangle casing
        # as some project/vendor specific parameters might be case-sensitive.
        assert data["links"] == [
            {
                "href": response.expect,
                "rel": "next",
                "type": "application/geo+json",
                "title": "next page",
            }
        ]

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&TYPENAMES=restaurant&outputformat=geojson"
        ),
        Post(
            f"""
            <GetFeature version="2.0.0" outputFormat="geojson" service="WFS" {XML_NS}>
            <Query typeNames="restaurant"></Query>
            </GetFeature>
            """
        ),
        url=Url.COMPLEX,
    )
    def test_get_geojson_complex(
        self, restaurant_m2m, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works for complex field types.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(3):
            assert response["content-type"] == "application/geo+json; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        data = read_json(content)

        assert data == {
            "type": "FeatureCollection",
            "links": [],
            "timeStamp": data["timeStamp"],
            "numberMatched": 2,
            "numberReturned": 2,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"},
            },
            "features": [
                {
                    "type": "Feature",
                    "id": f"restaurant.{restaurant_m2m.id}",
                    "geometry_name": "Café Noir",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point1_geojson,
                    },
                    "properties": {
                        "id": restaurant_m2m.id,
                        "name": "Café Noir",
                        "city": {
                            # City is expanded, following the type definition
                            "id": restaurant_m2m.city_id,
                            "name": "CloudCity",
                        },
                        "rating": 5.0,
                        "is_open": True,
                        "created": "2020-04-05T12:11:10+00:00",
                        "opening_hours": [
                            {
                                "weekday": 4,
                                "start_time": "16:00:00",
                                "end_time": "23:30:00",
                            },
                            {
                                "weekday": 5,
                                "start_time": "16:00:00",
                                "end_time": "23:30:00",
                            },
                            {
                                "weekday": 6,
                                "start_time": "20:00:00",
                                "end_time": "23:30:00",
                            },
                        ],
                        "tags": ["cafe", "black"],
                    },
                },
                {
                    "type": "Feature",
                    "id": f"restaurant.{bad_restaurant.id}",
                    "geometry_name": "Foo Bar",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point2_geojson,
                    },
                    "properties": {
                        "id": bad_restaurant.id,
                        "name": "Foo Bar",
                        "city": None,
                        "rating": 1.0,
                        "is_open": False,
                        "created": "2020-04-05T20:11:10+00:00",
                        "opening_hours": [],
                        "tags": None,
                    },
                },
            ],
        }

    @parametrize_response(
        Get(
            "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&TYPENAMES=restaurant&outputformat=geojson"
        ),
        Post(
            f"""
            <GetFeature version="2.0.0" outputFormat="geojson" service="WFS" {XML_NS}>
            <Query typeNames="restaurant"></Query>
            </GetFeature>
            """
        ),
        url=Url.FLAT,
    )
    def test_get_geojson_flattened(
        self, restaurant, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works for flattened field types."""
        with django_assert_max_num_queries(2):
            assert response["content-type"] == "application/geo+json; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        data = read_json(content)

        assert data == {
            "type": "FeatureCollection",
            "links": [],
            "timeStamp": data["timeStamp"],
            "numberMatched": 2,
            "numberReturned": 2,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"},
            },
            "features": [
                {
                    "type": "Feature",
                    "id": f"restaurant.{restaurant.id}",
                    "geometry_name": "Café Noir",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point1_geojson,
                    },
                    "properties": {
                        "id": restaurant.id,
                        "name": "Café Noir",
                        # City is flattened, following the type definition
                        "city-id": restaurant.city_id,
                        "city-name": "CloudCity",
                        "city-region": "OurRegion",
                        "rating": 5.0,
                        "is_open": True,
                        "created": "2020-04-05T12:11:10+00:00",
                        "tags": ["cafe", "black"],
                    },
                },
                {
                    "type": "Feature",
                    "id": f"restaurant.{bad_restaurant.id}",
                    "geometry_name": "Foo Bar",
                    "geometry": {
                        "type": "Point",
                        "coordinates": coordinates.point2_geojson,
                    },
                    "properties": {
                        "id": bad_restaurant.id,
                        "name": "Foo Bar",
                        "city-id": None,
                        "city-name": None,
                        "city-region": None,
                        "rating": 1.0,
                        "is_open": False,
                        "created": "2020-04-05T20:11:10+00:00",
                        "tags": None,
                    },
                },
            ],
        }
