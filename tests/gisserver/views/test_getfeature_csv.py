import pytest

from tests.utils import read_response

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    def test_get_csv(
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
        with django_assert_max_num_queries(3):
            response = client.get(
                "/v1/wfs/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
                "&outputformat=csv"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","city_id","location","rating","is_open","created"
"{restaurant.id}","Café Noir","{restaurant.city_id}","{coordinates.point1_ewkt}","5.0","True","2020-04-05 12:11:10+00:00"
"{bad_restaurant.id}","Foo Bar","","{coordinates.point2_ewkt}","1.0","False","2020-04-05 20:11:10+00:00"
""".lstrip()  # noqa: E501
        assert content == expect

    def test_get_csv_complex(
        self,
        client,
        restaurant_m2m,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the CSV export works, for complex results."""
        with django_assert_max_num_queries(2):
            response = client.get(
                "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=csv"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","city.id","city.name","location","rating","is_open","created"
"{restaurant_m2m.id}","Café Noir","{restaurant_m2m.city_id}","CloudCity","{coordinates.point1_ewkt}","5.0","True","2020-04-05 12:11:10+00:00"
"{bad_restaurant.id}","Foo Bar","","","{coordinates.point2_ewkt}","1.0","False","2020-04-05 20:11:10+00:00"
""".lstrip()  # noqa: E501
        assert content == expect
        assert "SRID=4326;" in content

    def test_get_csv_flattened(
        self,
        client,
        restaurant,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works, for flattened results."""
        with django_assert_max_num_queries(2):
            response = client.get(
                "/v1/wfs-flattened/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=csv"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        # NOTE: seeing a single space difference in the EWKT "POINT (coordinates)" output likely means
        # the code isn't using DB-rendering but Python-GDAL based rendering.
        expect = f"""
"id","name","city-id","city-name","city-region","location","rating","is_open","created"
"{restaurant.id}","Café Noir","{restaurant.city_id}","CloudCity","OurRegion","{coordinates.point1_ewkt}","5.0","True","2020-04-05 12:11:10+00:00"
"{bad_restaurant.id}","Foo Bar","","","","{coordinates.point2_ewkt}","1.0","False","2020-04-05 20:11:10+00:00"
""".lstrip()  # noqa: E501
        assert content == expect
        assert "SRID=4326;" in content

    def test_get_csv_related_geometry(
        self,
        client,
        restaurant,
        restaurant_review,
        bad_restaurant,
        bad_restaurant_review,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the geojson export works, for flattened results."""
        with django_assert_max_num_queries(3):
            response = client.get(
                "/v1/wfs-related-geometry/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurantReview&outputformat=csv"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        # NOTE: seeing a single space difference in the EWKT "POINT (coordinates)" output likely means
        # the code isn't using DB-rendering but Python-GDAL based rendering.
        expect = f"""
"id","restaurant.id","restaurant.name","restaurant.city.id","restaurant.city.name","restaurant.location","restaurant.rating","restaurant.is_open","restaurant.created","review"
"{restaurant_review.id}","{restaurant.id}","Café Noir","{restaurant.city_id}","CloudCity","{coordinates.point1_ewkt}","5.0","True","2020-04-05 12:11:10+00:00","Pretty good!"
"{bad_restaurant_review.id}","{bad_restaurant.id}","Foo Bar","","","{coordinates.point2_ewkt}","1.0","False","2020-04-05 20:11:10+00:00","Stay away!"
""".lstrip()  # noqa: E501
        assert content == expect
        assert "SRID=4326;" in content
