import django
import pytest

from tests.requests import Get, Post, Url, parametrize_response
from tests.utils import XML_NS, read_response

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant&outputformat=csv"),
        Post(
            f"""
                <GetFeature version="2.0.0" outputFormat="csv" service="WFS" {XML_NS}>
                <Query typeNames="restaurant"></Query>
                </GetFeature>
                """
        ),
    )
    def test_get_csv(
        self, restaurant, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the csv export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(3):
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","city_id","location","rating","is_open","created"
"{restaurant.id}","Café Noir","{restaurant.city_id}","{coordinates.point1_ewkt}","5.0","True","2020-04-05 12:11:10+00:00"
"{bad_restaurant.id}","Foo Bar","","{coordinates.point2_ewkt}","1.0","False","2020-04-05 20:11:10+00:00"
""".lstrip()  # noqa: E501
        assert content == expect

    @pytest.mark.skipif(
        django.VERSION < (5, 0), reason="GeneratedField is only available in Django >= 5"
    )
    def test_get_csv_generated_field(
        self,
        client,
        generated_field,
        django_assert_max_num_queries,
        coordinates,
    ):
        """Prove that the csv export works."""
        with django_assert_max_num_queries(3):
            response = client.get(
                "/v1/wfs-gen-field/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=modelwithgeneratedfields"
                "&outputformat=csv"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","name_reversed","geometry","geometry_translated"
"{generated_field.id}","Palindrome","emordnilaP","{coordinates.point1_ewkt}","{coordinates.translated_ewkt}"
""".lstrip()  # noqa: E501
        assert content == expect

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant&outputformat=csv"),
        Post(
            f"""
                <GetFeature version="2.0.0" outputFormat="csv" service="WFS" {XML_NS}>
                <Query typeNames="restaurant"></Query>
                </GetFeature>
                """
        ),
        url=Url.COMPLEX,
    )
    def test_get_csv_complex(
        self, restaurant_m2m, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the CSV export works, for complex results."""
        with django_assert_max_num_queries(2):
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

    @parametrize_response(
        Get("?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant&outputformat=csv"),
        Post(
            f"""
                <GetFeature version="2.0.0" outputFormat="csv" service="WFS" {XML_NS}>
                <Query typeNames="restaurant"></Query>
                </GetFeature>
                """
        ),
        url=Url.FLAT,
    )
    def test_get_csv_flattened(
        self, restaurant, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works, for flattened results."""
        with django_assert_max_num_queries(2):
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
