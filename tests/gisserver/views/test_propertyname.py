import orjson
import pytest

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


def read_response(response) -> str:
    # works for all HttpResponse subclasses.
    return b"".join(response).decode()


@pytest.mark.django_db
class TestPropertyName:
    """All tests for the PropertyName scenarios"""

    @staticmethod
    def read_json(content) -> dict:
        try:
            return orjson.loads(content)
        except orjson.JSONDecodeError as e:
            snippet = content[e.pos - 300 : e.pos + 300]
            snippet = snippet[snippet.index("\n") :]  # from last newline
            raise AssertionError(f"Parsing JSON failed: {e}\nNear: {snippet}") from None

    def test_propertyname_csv(
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
                "&outputformat=csv&propertyname=id,name,city_id,location,rating"
            )
            assert response["content-type"] == "text/csv; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        expect = f"""
"id","name","city_id","location","rating"
"{restaurant.id}","Café Noir","{restaurant.city_id}","{coordinates.point1_ewkt}","5.0"
"{bad_restaurant.id}","Foo Bar","","{coordinates.point2_ewkt}","1.0"
""".lstrip()  # noqa: E501
        assert content == expect

    def test_propertyname_geojson(
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
                "&outputformat=geojson&propertyname=id,name,city_id,rating,tags"
            )
            assert response["content-type"] == "application/geo+json; charset=utf-8"
            content = read_response(response)
            assert response.status_code == 200, content

        data = self.read_json(content)

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
                        "tags": None,
                    },
                },
            ],
        }
