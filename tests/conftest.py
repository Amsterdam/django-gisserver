from __future__ import annotations

import calendar
from collections.abc import Callable
from dataclasses import dataclass
from datetime import time, timedelta
from decimal import Decimal
from typing import cast
from xml.etree import ElementTree

import django
import pytest
from django.contrib.gis.gdal import gdal_full_version
from django.contrib.gis.geos import Point, geos_version
from django.contrib.gis.geos.geometry import GEOSGeometry
from django.db import connection
from django.http.response import HttpResponseBase
from psycopg2 import Binary

from gisserver import conf
from gisserver.parsers import ows
from gisserver.parsers.xml import xmlns
from tests import xsd_download
from tests.requests import Request
from tests.test_gisserver import models
from tests.utils import NAMESPACES, RD_NEW, read_json


def pytest_configure():
    gdal_ver = gdal_full_version().decode()
    geos_ver = geos_version().decode()
    print(f'Running with Django {django.__version__}, GDAL="{gdal_ver}" GEOS="{geos_ver}"')
    print(f"Using GISSERVER_USE_DB_RENDERING={conf.GISSERVER_USE_DB_RENDERING}")

    for url in (
        "https://www.w3.org/2012/04/XMLSchema.xsd",
        "http://schemas.opengis.net/wfs/2.0/wfs.xsd",
        "http://schemas.opengis.net/gml/3.2.1/gml.xsd",
    ):
        if xsd_download.has_file(url):
            print(f"Found cached {url} at {xsd_download.XSD_ROOT}")
        else:
            print(f"Caching {url} to {xsd_download.XSD_ROOT}")
            xsd_download.download_schema(url)


@dataclass
class CoordinateInputs:
    point1_rd = Point(122411, 486250, srid=RD_NEW.srid)
    point2_rd = Point(199709, 307385, srid=RD_NEW.srid)

    point1_wgs84: Point  # How GeoDjango retrieved the object from the database
    point1_ewkt: str
    point1_geojson: list[Decimal]
    point1_xml_wgs84: str
    point1_xml_rd: str

    translated_wgs84: Point  # How GeoDjango retrieved the object from the database
    translated_ewkt: str
    translated_geojson: list[Decimal]
    translated_xml_wgs84: str
    translated_xml_envelope: tuple[str, str]

    point2_wgs84: Point  # Retrieved from db.
    point2_ewkt: str
    point2_geojson: list[Decimal]
    point2_xml_wgs84: str

    @property
    def bbox(self) -> str:
        """Provide an extent in which both coordinates exist."""
        return ",".join(map(str, (self.point1_wgs84 | self.point2_wgs84).extent))


def _get_point(hex_ewkb: str) -> Point:
    # Do what the GeoDjango conversion does with the PostGIS data object.
    return cast(Point, GEOSGeometry(hex_ewkb))


def _get_coordinates_text(point: Point) -> str:
    """Extract the coordinates from a GEOS Point"""
    return " ".join(map(str, point.coords))


def _get_geojson_coordinates(value: str) -> list[Decimal]:
    """Extract the coordinates from a GeoJSON point"""
    return read_json(value)["coordinates"]


def _parse_gml(xml: str) -> ElementTree.Element:
    """Feed a GML fragment without any namespacing to the parser."""
    end_first = xml.index(">")
    xml = f'{xml[:end_first]} xmlns:gml="{xmlns.gml32}"{xml[end_first:]}'
    return ElementTree.fromstring(xml)


def _get_gml_coordinates(xml: str) -> str:
    """Extract the coordinates from a GML Point"""
    tree = _parse_gml(xml)
    coordinates = tree.findtext("gml:pos", namespaces=NAMESPACES)
    return coordinates.replace(",", " ")


def _get_gml_envelope(xml: str) -> tuple[str, str]:
    tree = _parse_gml(xml)
    return [
        tree.findtext("gml:lowerCorner", namespaces=NAMESPACES),
        tree.findtext("gml:upperCorner", namespaces=NAMESPACES),
    ]


@pytest.fixture(scope="session")
def coordinates(db_coordinates, python_coordinates):
    if conf.GISSERVER_USE_DB_RENDERING:
        # Database rendering mode: all coordinates are calculated by PostGIS definitions,
        # using the proj/gdal libraries linked to PostGIS and the spatial_ref_sys table.
        return db_coordinates
    else:
        # Python rendering mode: everything happens with the locally
        # linked proj/gdal library and its bundled transformation rules.
        return python_coordinates


@pytest.fixture(scope="session")
def db_coordinates(django_db_setup, django_db_blocker):
    """Calculate what PostgreSQL would produce.

    Despite efforts to sync the PROJ.4 definitions, minor differences between platforms remain.
    So the values are calculated beforehand, so the expected data is included in the tests.
    """
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        point1 = "ST_GeomFromEWKB(%(point1)s)"
        point2 = "ST_GeomFromEWKB(%(point2)s)"
        point1_wgs84 = f"ST_Transform({point1}, 4326)"
        point2_wgs84 = f"ST_Transform({point2}, 4326)"
        point1_rd = f"ST_Transform({point1_wgs84}, 28992)"  # back and forth conversion in DB
        point1_translated = f"ST_Translate({point1_wgs84}, 1, 1)"
        pr = conf.GISSERVER_DB_PRECISION

        cursor.execute(
            "SELECT"
            f" {point1_wgs84} as point1_wgs84,"
            f" {point1_translated} as translated_wgs84,"
            f" ST_AsEWKT({point1_wgs84}, {pr}) as point1_ewkt,"
            f" ST_AsEWKT({point1_translated}, {pr}) as translated_ewkt,"
            f" ST_AsGeoJson({point1_wgs84}, {pr}) as point1_geojson,"
            f" ST_AsGeoJson({point1_translated}, {pr}) as translated_geojson,"
            f" ST_AsGML(3, {point1_wgs84}, {pr}, 1) as point1_xml_wgs84,"
            f" ST_AsGML(3, {point1_translated}, {pr}, 1) as translated_xml_wgs84,"
            f" ST_AsGML(3, ST_Union({point1_wgs84}, {point1_translated}), {pr}, 33) as translated_xml_envelope,"
            f" ST_AsGML(3, {point1_rd}, {pr}, 1) as point1_xml_rd,"
            # Point 2
            f" {point2_wgs84} as point2_wgs84,"
            f" ST_AsEWKT({point2_wgs84}, {pr}) as point2_ewkt,"
            f" ST_AsGeoJson({point2_wgs84}, {pr}) as point2_geojson,"
            f" ST_AsGML(3, {point2_wgs84}, {pr}, 1) as point2_xml_wgs84",
            {
                "point1": Binary(CoordinateInputs.point1_rd.ewkb),
                "point2": Binary(CoordinateInputs.point2_rd.ewkb),
            },
        )

        columns = (x.name for x in cursor.description)
        result = cursor.fetchone()
        result = dict(zip(columns, result))

        return CoordinateInputs(
            point1_wgs84=_get_point(result["point1_wgs84"]),
            point1_ewkt=result["point1_ewkt"],
            point1_geojson=_get_geojson_coordinates(result["point1_geojson"]),
            point1_xml_wgs84=_get_gml_coordinates(result["point1_xml_wgs84"]),
            point1_xml_rd=_get_gml_coordinates(result["point1_xml_rd"]),
            translated_wgs84=_get_point(result["translated_wgs84"]),
            translated_ewkt=result["translated_ewkt"],
            translated_geojson=_get_geojson_coordinates(result["translated_geojson"]),
            translated_xml_wgs84=_get_gml_coordinates(result["translated_xml_wgs84"]),
            # Strangely, the DB rendering will have a different envelope, not literally both points.
            translated_xml_envelope=_get_gml_envelope(result["translated_xml_envelope"]),
            point2_wgs84=_get_point(result["point2_wgs84"]),
            point2_ewkt=result["point2_ewkt"],
            point2_geojson=_get_geojson_coordinates(result["point2_geojson"]),
            point2_xml_wgs84=_get_gml_coordinates(result["point2_xml_wgs84"]),
        )


@pytest.fixture(scope="session")
def python_coordinates(db_coordinates):
    """Calculate what our local proj4/gdal library would produce."""
    # As base, use how the database would return the stored object.
    # Saving a RD-NEW coordinate in the database will transform the data to WGS84 on saving,
    # but this happens inside the database itself as the SRID of the field differs from the input.
    point1_wgs84 = db_coordinates.point1_wgs84
    translated_wgs84 = db_coordinates.translated_wgs84
    point2_wgs84 = db_coordinates.point2_wgs84

    point1_rd_back = RD_NEW.apply_to(point1_wgs84, clone=True)
    return CoordinateInputs(
        point1_wgs84=point1_wgs84,  # How data from PointField is returned
        point1_ewkt=point1_wgs84.ewkt,
        point1_geojson=_get_geojson_coordinates(point1_wgs84.json),
        point1_xml_wgs84=_get_coordinates_text(point1_wgs84),
        point1_xml_rd=_get_coordinates_text(point1_rd_back),
        translated_wgs84=translated_wgs84,  # How data from PointField is returned
        translated_ewkt=translated_wgs84.ewkt,
        translated_geojson=_get_geojson_coordinates(translated_wgs84.json),
        translated_xml_wgs84=_get_coordinates_text(translated_wgs84),
        translated_xml_envelope=[
            # Literally calculated as the box of both points
            _get_coordinates_text(point1_wgs84),
            _get_coordinates_text(translated_wgs84),
        ],
        point2_wgs84=point2_wgs84,  # How data from PointField is returned
        point2_ewkt=point2_wgs84.ewkt,
        point2_geojson=_get_geojson_coordinates(point2_wgs84.json),
        point2_xml_wgs84=_get_coordinates_text(point2_wgs84),
    )


@pytest.fixture()
def city() -> models.City:
    return models.City.objects.create(name="CloudCity", region="OurRegion")


@pytest.fixture()
def restaurant(city) -> models.Restaurant:
    return models.Restaurant.objects.create(
        name="Café Noir",
        city=city,
        location=CoordinateInputs.point1_rd,
        rating=5.0,
        is_open=True,
        tags=["cafe", "black"],
    )


@pytest.fixture()
def restaurant_m2m(restaurant) -> models.Restaurant:
    restaurant.opening_hours.add(
        models.OpeningHour.objects.create(weekday=calendar.FRIDAY),
        models.OpeningHour.objects.create(weekday=calendar.SATURDAY),
        models.OpeningHour.objects.create(weekday=calendar.SUNDAY, start_time=time(20, 0)),
    )
    return restaurant


@pytest.fixture()
def bad_restaurant() -> models.Restaurant:
    return models.Restaurant.objects.create(
        name="Foo Bar",
        location=CoordinateInputs.point2_rd,
        rating=1.0,
        is_open=False,
        created=models.current_datetime() + timedelta(hours=8),
    )


@pytest.fixture()
def restaurant_review(restaurant) -> models.RestaurantReview:
    return models.RestaurantReview.objects.create(restaurant=restaurant, review="Pretty good!")


@pytest.fixture()
def bad_restaurant_review(bad_restaurant) -> models.RestaurantReview:
    return models.RestaurantReview.objects.create(restaurant=bad_restaurant, review="Stay away!")


if django.VERSION >= (5, 0):

    @pytest.fixture()
    def generated_field() -> models.ModelWithGeneratedFields:
        return models.ModelWithGeneratedFields.objects.create(
            name="Palindrome", geometry=CoordinateInputs.point1_rd
        )


@pytest.fixture()
def empty_restaurant() -> models.Restaurant:
    return models.Restaurant.objects.create(name="Empty")


@pytest.fixture()
def many_restaurants() -> None:
    for i in range(15):
        models.Restaurant.objects.bulk_create(
            [models.Restaurant(name=f"obj#{i * j}") for j in range(100)]
        )


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Still show which version the tests run against.
    This allows to debug issues with older GDAL / proj version.
    """
    with django_db_blocker.unblock(), connection.cursor() as c:
        # Show the postgis version for debugging
        c.callproc("postgis_full_version")  # SELECT postgis_full_version()
        result = c.fetchone()[0]
        print(f"Postgresql setup: {result}")

        # By fetching this first, it won't pollute django_assert_max_num_queries()
        _ = connection.ops.spatial_version


@pytest.fixture()
def response(client, request) -> HttpResponseBase | Callable[..., HttpResponseBase]:
    """This fixture can be used to abstract over different types of requests (GET/POST) with
    different kinds of urls expecting similar outcomes.

    Delaying the call (in which case it returns a function returning a response instead of a
    response) and adding expect attributes are both possible.

    Usage::

        @parametrize_response(
            Get("?query=test"),
            Get(lambda id: f"?query=test{id}", url=Url.COMPLEX),
            Post("<xml></xml>"),
            Post("<xml></xml>", expect=AssertionError),
            url=Url.FLAT,
        )
        def test_function(response):
            ...
    """
    req: Request = request.param
    response = req.get_response(client)
    response.expect = req.expect
    return response


@pytest.fixture()
def ows_request(request) -> ows.BaseOwsRequest:
    """This fixture can be used to abstract over different types of requests (GET/POST) with
    different kinds of urls expecting similar outcomes.

    Delaying the call (in which case it returns a function returning a response instead of a
    response) and adding expect attributes are both possible.

    Usage::

        @parametrize_ows_request(
            Get("?query=test"),
            Get(lambda id: f"?query=test{id}"),
            Post("<xml></xml>"),
            Post("<xml></xml>", expect=AssertionError),
        )
        def test_function(ows_request):
            ...
    """
    req: Request = request.param
    ows_req = req.get_ows_request()

    ows_req.method = req.__class__.__name__.upper()
    if req.expect:
        ows_req.expect = req.expect
    return ows_req
