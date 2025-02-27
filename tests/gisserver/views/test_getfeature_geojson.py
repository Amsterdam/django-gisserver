import django
import pytest

from gisserver import conf
from tests.test_gisserver.models import Restaurant
from tests.utils import read_json, read_response

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    def test_get_geojson(
        self,
        client,
        restaurant,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(2):
            response = client.get(
                "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                "&outputformat=geojson"
            )
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
                "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
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
        expected_coordinates = [x + 1.0 for x in coordinates.point1_geojson]

        assert data["features"][0]["geometry"]["coordinates"] == expected_coordinates
        assert data == {
            "type": "FeatureCollection",
            "links": [],
            "timeStamp": data["timeStamp"],
            "numberMatched": 1,
            "numberReturned": 1,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
            },
            "features": [
                {
                    "type": "Feature",
                    "id": f"modelwithgeneratedfields.{generated_field.id}",
                    "geometry_name": "Palindrome",
                    "geometry": {
                        "type": "Point",
                        "coordinates": expected_coordinates,
                    },
                    "properties": {
                        "id": generated_field.id,
                        "name": "Palindrome",
                        "name_reversed": "emordnilaP",
                    },
                },
            ],
        }

    @pytest.mark.parametrize("use_count", [1, 0])
    def test_get_geojson_pagination(
        self, client, use_count, monkeypatch, django_assert_max_num_queries
    ):
        """Prove that the geojson export handles pagination.

        Two variations are tested; when normal COUNT happens,
        or a sentinel object is used to detect there are more results.
        """
        monkeypatch.setattr(conf, "GISSERVER_COUNT_NUMBER_MATCHED", use_count)

        # Create a large set so the buffer needs to flush.
        for i in range(1500):
            Restaurant.objects.create(name=f"obj#{i}")

        with django_assert_max_num_queries(1 + use_count):
            response = client.get(
                "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                "&vendor-arg=foobar&outputformat=geojson&COUNT=1000"
            )
            assert (
                response["content-type"] == "application/geo+json; charset=utf-8"
            )  # before stream starts
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
                "href": (
                    "http://testserver/v1/wfs/"
                    "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                    "&vendor-arg=foobar"
                    "&outputformat=geojson&COUNT=1000&STARTINDEX=1000"
                ),
                "rel": "next",
                "type": "application/geo+json",
                "title": "next page",
            }
        ]

    def test_get_geojson_complex(
        self,
        client,
        restaurant_m2m,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works for complex field types.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(3):
            response = client.get(
                "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=geojson"
            )
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
                "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
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

    def test_get_geojson_flattened(
        self,
        client,
        restaurant,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works for flattened field types."""
        with django_assert_max_num_queries(2):
            response = client.get(
                "/v1/wfs-flattened/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=geojson"
            )
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
                "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
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
