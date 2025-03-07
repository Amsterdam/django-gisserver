import pytest

from tests.constants import XML_NS
from tests.requests import Get, Post, parametrize_response
from tests.utils import read_response

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestGetFeature:
    """All tests for the GetFeature method.
    The methods need to have at least one datatype, otherwise not all content is rendered.
    """

    @parametrize_response(
        [
            Get(
                "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant&outputformat=csv"
            ),
            Post(
                f"""
                <GetFeature version="2.0.0" outputFormat="csv" service="WFS" {XML_NS}>
                <Query typeNames="restaurant"></Query>
                </GetFeature>
                """
            ),
        ]
    )
    def test_get_csv(
        self, restaurant, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works.

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

    @parametrize_response(
        [
            Get(
                "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant&outputformat=csv"
            ),
            Post(
                f"""
                <GetFeature version="2.0.0" outputFormat="csv" service="WFS" {XML_NS}>
                <Query typeNames="restaurant"></Query>
                </GetFeature>
                """
            ),
        ],
        url_type="COMPLEX",
    )
    def test_get_csv_complex(
        self, restaurant_m2m, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the CSV export works, for complex results."""
        with django_assert_max_num_queries(1):
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
        [
            Get(
                "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant&outputformat=csv"
            ),
            Post(
                f"""
                <GetFeature version="2.0.0" outputFormat="csv" service="WFS" {XML_NS}>
                <Query typeNames="restaurant"></Query>
                </GetFeature>
                """
            ),
        ],
        url_type="FLAT",
    )
    def test_get_csv_flattened(
        self, restaurant, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works, for flattened results."""
        with django_assert_max_num_queries(1):
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","city-id","city-name","city-region","location","rating","is_open","created"
"{restaurant.id}","Café Noir","{restaurant.city_id}","CloudCity","OurRegion","{coordinates.point1_ewkt}","5.0","True","2020-04-05 12:11:10+00:00"
"{bad_restaurant.id}","Foo Bar","","","","{coordinates.point2_ewkt}","1.0","False","2020-04-05 20:11:10+00:00"
""".lstrip()  # noqa: E501
        assert content == expect
        assert "SRID=4326;" in content
