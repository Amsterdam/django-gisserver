import django
import pytest
from django.conf import settings

from tests.requests import Get, Post, Url, parametrize_response
from tests.utils import (
    WFS_20_XSD,
    XML_NS,
    assert_xml_equal,
    get_sql,
    read_json,
    read_response,
    validate_xsd,
)

# enable for all tests in this file
pytestmark = [pytest.mark.urls("tests.test_gisserver.urls")]


@pytest.mark.django_db
class TestPropertyName:
    """All tests for the PropertyName scenarios"""

    @parametrize_response(
        Get(
            lambda: "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&propertyname=name,city_id"
        ),
        Post(
            lambda: f"""
                <GetFeature service="WFS" version="2.0.0" {XML_NS}>
                    <Query typeNames="restaurant">
                    <PropertyName>name</PropertyName>
                    <PropertyName>city_id</PropertyName>
                    </Query>
                </GetFeature>
                """
        ),
    )
    def test_propertyname_gml(
        self, restaurant, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(1) as queries:
            res = response()
            content = read_response(res)
        assert res["content-type"] == "text/xml; charset=utf-8", content
        assert res.status_code == 200, content
        assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"

        # See whether our feature is rendered
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection
            xmlns:app="http://example.org/gisserver"
            xmlns:gml="http://www.opengis.net/gml/3.2"
            xmlns:wfs="http://www.opengis.net/wfs/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=app:restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
            timeStamp="{timestamp}" numberMatched="2" numberReturned="2">
    <wfs:member>
      <app:restaurant gml:id="restaurant.{restaurant.id}">
        <app:name>Café Noir</app:name>
        <app:city_id>{restaurant.city_id}</app:city_id>
      </app:restaurant>
    </wfs:member>
    <wfs:member>
      <app:restaurant gml:id="restaurant.{bad_restaurant.id}">
        <app:name>Foo Bar</app:name>
        <app:city_id xsi:nil="true"/>
      </app:restaurant>
    </wfs:member>
  </wfs:FeatureCollection>""",  # noqa: E501
        )

        # Prove that only the required fields were queried
        assert queries[0]["sql"] == (
            "SELECT"
            ' "test_gisserver_restaurant"."id",'
            ' "test_gisserver_restaurant"."name",'
            ' "test_gisserver_restaurant"."city_id" '
            'FROM "test_gisserver_restaurant" '
            'ORDER BY "test_gisserver_restaurant"."id" ASC '
            "LIMIT 5000"
        )

    @parametrize_response(
        Get(
            lambda: "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&PROPERTYNAME=name,city/name,opening_hours/weekday,opening_hours/start_time",
            url=Url.COMPLEX,
        ),
        Post(
            lambda: f"""
                <GetFeature service="WFS" version="2.0.0" {XML_NS}>
                    <Query typeNames="restaurant">
                    <PropertyName>name</PropertyName>
                    <PropertyName>city/name</PropertyName>
                    <PropertyName>opening_hours/weekday</PropertyName>
                    <PropertyName>opening_hours/start_time</PropertyName>
                    </Query>
                </GetFeature>
                """,
            url=Url.COMPLEX,
            validate_xml=False,  # PropertyName should officially be an QName only!
        ),
    )
    def test_propertyname_gml_complex(
        self,
        restaurant_m2m,
        bad_restaurant,
        django_assert_max_num_queries,
        coordinates,
        response,
    ):
        """Prove that rendering complex types works."""
        with django_assert_max_num_queries(3) as queries:
            res = response()
            content = read_response(res)
            assert res["content-type"] == "text/xml; charset=utf-8", content
            assert res.status_code == 200, content
            assert "</wfs:FeatureCollection>" in content

        # Validate against the WFS 2.0 XSD
        xml_doc = validate_xsd(content, WFS_20_XSD)
        assert xml_doc.attrib["numberMatched"] == "2"
        assert xml_doc.attrib["numberReturned"] == "2"

        # See whether our feature is rendered
        timestamp = xml_doc.attrib["timeStamp"]

        assert_xml_equal(
            content,
            f"""<wfs:FeatureCollection
   xmlns:app="http://example.org/gisserver"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   xmlns:wfs="http://www.opengis.net/wfs/2.0"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:schemaLocation="http://example.org/gisserver http://testserver/v1/wfs-complextypes/?SERVICE=WFS&amp;VERSION=2.0.0&amp;REQUEST=DescribeFeatureType&amp;TYPENAMES=app:restaurant http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd"
   timeStamp="{timestamp}" numberMatched="2" numberReturned="2">

    <wfs:member>
      <app:restaurant gml:id="restaurant.{restaurant_m2m.id}">
        <app:name>Café Noir</app:name>
        <app:city>
          <app:name>CloudCity</app:name>
        </app:city>
        <app:opening_hours>
          <app:weekday>4</app:weekday>
          <app:start_time>16:00:00</app:start_time>
        </app:opening_hours>
        <app:opening_hours>
          <app:weekday>5</app:weekday>
          <app:start_time>16:00:00</app:start_time>
        </app:opening_hours>
        <app:opening_hours>
          <app:weekday>6</app:weekday>
          <app:start_time>20:00:00</app:start_time>
        </app:opening_hours>
      </app:restaurant>
    </wfs:member>

    <wfs:member>
      <app:restaurant gml:id="restaurant.{bad_restaurant.id}">
        <app:name>Foo Bar</app:name>
        <app:city xsi:nil="true" />
      </app:restaurant>
    </wfs:member>

</wfs:FeatureCollection>""",  # noqa: E501
        )

        # Prove that only the needed elements are retrieved
        sql = get_sql(queries)
        assert sql == [
            (
                "SELECT"
                ' "test_gisserver_restaurant"."id",'
                ' "test_gisserver_restaurant"."name",'
                ' "test_gisserver_restaurant"."city_id"'
                ' FROM "test_gisserver_restaurant"'
                ' ORDER BY "test_gisserver_restaurant"."id" ASC'
                " LIMIT 5000"
            ),
            (
                "SELECT"
                ' "test_gisserver_city"."id",'
                ' "test_gisserver_city"."name"'
                ' FROM "test_gisserver_city"'
                f' WHERE "test_gisserver_city"."id" IN ({restaurant_m2m.city_id})'
            ),
            (
                "SELECT"
                ' ("test_gisserver_restaurant_opening_hours"."restaurant_id") AS "_prefetch_related_val_restaurant_id",'
                ' "test_gisserver_openinghour"."id",'
                ' "test_gisserver_openinghour"."weekday",'
                ' "test_gisserver_openinghour"."start_time"'
                ' FROM "test_gisserver_openinghour"'
                ' INNER JOIN "test_gisserver_restaurant_opening_hours"'
                ' ON ("test_gisserver_openinghour"."id" = "test_gisserver_restaurant_opening_hours"."openinghour_id")'
                f' WHERE "test_gisserver_restaurant_opening_hours"."restaurant_id" IN ({restaurant_m2m.id}, {bad_restaurant.id})'
                ' ORDER BY "test_gisserver_openinghour"."weekday" ASC'
            ),
        ]

    @parametrize_response(
        Get(
            lambda: "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&outputformat=geojson&propertyname=id,name,city_id,rating,tags"
        ),
        Post(
            lambda: f"""
                <GetFeature service="WFS" version="2.0.0" outputFormat="geojson"  {XML_NS}>
                    <Query typeNames="restaurant">
                    <PropertyName>id</PropertyName>
                    <PropertyName>name</PropertyName>
                    <PropertyName>city_id</PropertyName>
                    <PropertyName>rating</PropertyName>
                    <PropertyName>tags</PropertyName>
                    </Query>
                </GetFeature>
                """
        ),
    )
    def test_propertyname_geojson(
        self, restaurant, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(2):
            res = response()
            assert res["content-type"] == "application/geo+json; charset=utf-8"
            content = read_response(res)
            assert res.status_code == 200, content

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

    @parametrize_response(
        Get(
            lambda: "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
            "&TYPENAMES=restaurant&outputformat=geojson"
            "&PROPERTYNAME=name,city/name,opening_hours/weekday,opening_hours/start_time",
            url=Url.COMPLEX,
        ),
        Post(
            lambda: f"""
                <GetFeature service="WFS" version="2.0.0" outputFormat="geojson"  {XML_NS}>
                    <Query typeNames="restaurant">
                    <PropertyName>name</PropertyName>
                    <PropertyName>city/name</PropertyName>
                    <PropertyName>opening_hours/weekday</PropertyName>
                    <PropertyName>opening_hours/start_time</PropertyName>
                    </Query>
                </GetFeature>
                """,
            url=Url.COMPLEX,
            validate_xml=False,  # PropertyName should officially be an QName only!
        ),
    )
    def test_propertyname_geojson_complex(
        self, restaurant_m2m, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works for complex field types.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(3) as queries:
            res = response()
            assert res["content-type"] == "application/geo+json; charset=utf-8"
            content = read_response(res)
            assert res.status_code == 200, content

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
                    "id": f"restaurant.{restaurant_m2m.id}",  # global id still used
                    "geometry_name": "Café Noir",
                    "geometry": {
                        # Geometry is always included
                        "type": "Point",
                        "coordinates": coordinates.point1_geojson,
                    },
                    "properties": {
                        # 'id' removed here
                        "name": "Café Noir",
                        "city": {
                            # no id, only name
                            # City is expanded, following the type definition
                            "name": "CloudCity",
                        },
                        "opening_hours": [
                            {
                                "weekday": 4,
                                "start_time": "16:00:00",
                            },
                            {
                                "weekday": 5,
                                "start_time": "16:00:00",
                            },
                            {
                                "weekday": 6,
                                "start_time": "20:00:00",
                            },
                        ],
                    },
                },
                {
                    "type": "Feature",
                    "id": f"restaurant.{bad_restaurant.id}",  # global id still used
                    "geometry_name": "Foo Bar",
                    "geometry": {
                        # Geometry is always included
                        "type": "Point",
                        "coordinates": coordinates.point2_geojson,
                    },
                    "properties": {
                        # 'id' removed here
                        "name": "Foo Bar",
                        "city": None,
                        "opening_hours": [],
                    },
                },
            ],
        }

        if settings.GISSERVER_USE_DB_RENDERING:
            # https://code.djangoproject.com/ticket/34882
            options = ", 0" if django.VERSION >= (5, 0) else ""
            location_sql = f'ST_AsGeoJSON("test_gisserver_restaurant"."location", 15{options}) AS "_as_db_geojson"'
        else:
            location_sql = '"test_gisserver_restaurant"."location"::bytea'

        # Prove only the needed fields were retrieved
        sql = get_sql(queries)
        assert sql == [
            (
                "SELECT"
                ' "test_gisserver_restaurant"."id",'
                ' "test_gisserver_restaurant"."name",'
                ' "test_gisserver_restaurant"."city_id",'
                f" {location_sql}"
                ' FROM "test_gisserver_restaurant"'
                ' ORDER BY "test_gisserver_restaurant"."id" ASC'
            ),
            (
                "SELECT"
                ' "test_gisserver_city"."id",'
                ' "test_gisserver_city"."name"'
                ' FROM "test_gisserver_city"'
                f' WHERE "test_gisserver_city"."id" IN ({restaurant_m2m.city_id})'
            ),
            (
                "SELECT"
                ' ("test_gisserver_restaurant_opening_hours"."restaurant_id") AS "_prefetch_related_val_restaurant_id",'
                ' "test_gisserver_openinghour"."id",'
                ' "test_gisserver_openinghour"."weekday",'
                ' "test_gisserver_openinghour"."start_time"'
                ' FROM "test_gisserver_openinghour"'
                ' INNER JOIN "test_gisserver_restaurant_opening_hours"'
                ' ON ("test_gisserver_openinghour"."id" = "test_gisserver_restaurant_opening_hours"."openinghour_id")'
                f' WHERE "test_gisserver_restaurant_opening_hours"."restaurant_id" IN ({restaurant_m2m.id}, {bad_restaurant.id})'
                ' ORDER BY "test_gisserver_openinghour"."weekday" ASC'
            ),
        ]

    @parametrize_response(
        Get(
            lambda: "?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant"
            "&outputformat=csv&propertyname=id,name,city_id,location,rating"
        ),
        Post(
            lambda: f"""
                <GetFeature service="WFS" version="2.0.0" outputFormat="csv"  {XML_NS}>
                    <Query typeNames="restaurant">
                    <PropertyName>id</PropertyName>
                    <PropertyName>name</PropertyName>
                    <PropertyName>city_id</PropertyName>
                    <PropertyName>location</PropertyName>
                    <PropertyName>rating</PropertyName>
                    </Query>
                </GetFeature>
                """
        ),
    )
    def test_propertyname_csv(
        self, restaurant, bad_restaurant, django_assert_max_num_queries, coordinates, response
    ):
        """Prove that the geojson export works.

        Including 2 objects to prove that the list rendering
        also includes comma's properly.
        """
        with django_assert_max_num_queries(1):
            res = response()
            assert res["content-type"] == "text/csv; charset=utf-8"
            content = read_response(res)
            assert res.status_code == 200, content

        expect = f"""
"id","name","city_id","location","rating"
"{restaurant.id}","Café Noir","{restaurant.city_id}","{coordinates.point1_ewkt}","5.0"
"{bad_restaurant.id}","Foo Bar","","{coordinates.point2_ewkt}","1.0"
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
        """Prove that the CSV export works, for complex results (this can't return M2M data)."""
        with django_assert_max_num_queries(3):
            response = client.get(
                "/v1/wfs-complextypes/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0"
                "&TYPENAMES=restaurant&outputformat=csv"
                "&PROPERTYNAME=name,city/name"
            )
            assert response["content-type"] == "text/csv; charset=utf-8", response
            content = read_response(response)
            assert response.status_code == 200, content

        expect = """
"name","city.name"
"Café Noir","CloudCity"
"Foo Bar",""
""".lstrip()  # noqa: E501
        assert content == expect
