from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

import django
import orjson
import pytest
from django.contrib.gis.gdal import gdal_full_version
from django.contrib.gis.geos import Point, geos_version
from django.contrib.gis.geos.geometry import GEOSGeometry
from django.db import connection
from psycopg2 import Binary

from gisserver import conf
from gisserver.types import GML32
from tests.constants import RD_NEW, RD_NEW_SRID
from tests.test_gisserver.models import City, OpeningHour, Restaurant, current_datetime
from tests.xsd_download import download_schema

HERE = Path(__file__).parent
XSD_ROOT = HERE.joinpath("files/xsd")


def pytest_configure():
    gdal_ver = gdal_full_version().decode()
    geos_ver = geos_version().decode()
    print(f'Running with Django {django.__version__}, GDAL="{gdal_ver}" GEOS="{geos_ver}"')
    print(f"Using GISSERVER_USE_DB_RENDERING={conf.GISSERVER_USE_DB_RENDERING}")

    for url in (
        "http://schemas.opengis.net/wfs/2.0/wfs.xsd",
        "http://schemas.opengis.net/gml/3.2.1/gml.xsd",
    ):
        if not XSD_ROOT.joinpath(url.replace("http://", "")).exists():
            print(f"Caching {url} to {XSD_ROOT.absolute()}")
            download_schema(url)


@dataclass
class CoordinateInputs:
    point1_rd = Point(122411, 486250, srid=RD_NEW_SRID)
    point2_rd = Point(199709, 307385, srid=RD_NEW_SRID)

    point1_wgs84: Point  # How GeoDjango retrieved the object from the database
    point1_ewkt: str
    point1_geojson: list[Decimal]
    point1_xml_wgs84: str
    point1_xml_rd: str

    point2_wgs84: Point  # Retrieved from db.
    point2_ewkt: str
    point2_geojson: list[Decimal]
    point2_xml_wgs84: str


def _get_point(hex_ewkb: str) -> Point:
    # Do what the GeoDjango conversion does with the PostGIS data object.
    return cast(Point, GEOSGeometry(hex_ewkb))


def _get_geojson(value: str) -> list[Decimal]:
    """Extract the coordinates from a GeoJSON point"""
    return orjson.loads(value)["coordinates"]


def _get_gml(xml: str) -> str:
    """Extract the coordinates from a GML Point"""
    end_first = xml.index(">")
    xml = f'{xml[:end_first]} xmlns:gml="{GML32}"{xml[end_first:]}'
    tree = ElementTree.fromstring(xml)
    return tree.findtext("gml:pos", namespaces={"gml": GML32}).replace(",", " ")


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
        pr = conf.GISSERVER_DB_PRECISION

        cursor.execute(
            "SELECT"
            f" ST_Transform({point1}, 4326) as point1_wgs84,"
            f" ST_AsEWKT(ST_Transform({point1}, 4326), {pr}) as point1_ewkt,"
            f" ST_AsGeoJson(ST_Transform({point1}, 4326), {pr}) as point1_geojson,"
            f" ST_AsGML(3, ST_Transform({point1}, 4326), {pr}, 1) as point1_xml_wgs84,"
            f" ST_AsGML(3, ST_Transform(ST_Transform({point1}, 4326), 28992), {pr}, 1) as point1_xml_rd,"  # noqa: E501
            f" ST_Transform({point2}, 4326) as point2_wgs84,"
            f" ST_AsEWKT(ST_Transform({point2}, 4326), {pr}) as point2_ewkt,"
            f" ST_AsGeoJson(ST_Transform({point2}, 4326), {pr}) as point2_geojson,"
            f" ST_AsGML(3, ST_Transform({point2}, 4326), {pr}, 1) as point2_xml_wgs84",
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
            point1_geojson=_get_geojson(result["point1_geojson"]),
            point1_xml_wgs84=_get_gml(result["point1_xml_wgs84"]),
            point1_xml_rd=_get_gml(result["point1_xml_rd"]),
            point2_wgs84=_get_point(result["point2_wgs84"]),
            point2_ewkt=result["point2_ewkt"],
            point2_geojson=_get_geojson(result["point2_geojson"]),
            point2_xml_wgs84=_get_gml(result["point2_xml_wgs84"]),
        )


@pytest.fixture(scope="session")
def python_coordinates(db_coordinates):
    """Calculate what our local proj4/gdal library would produce."""
    # As base, use how the database would return the stored object.
    # Saving a RD-NEW coordinate in the database will transform the data to WGS84 on saving,
    # but this happens inside the database itself as the SRID of the field differs from the input.
    point1_wgs84 = db_coordinates.point1_wgs84
    point2_wgs84 = db_coordinates.point2_wgs84

    point1_rd_back = RD_NEW.apply_to(point1_wgs84, clone=True)
    return CoordinateInputs(
        point1_wgs84=point1_wgs84,  # How data from PointField is returned
        point1_ewkt=point1_wgs84.ewkt,
        point1_geojson=_get_geojson(point1_wgs84.json),
        point1_xml_wgs84=" ".join(map(str, point1_wgs84.coords)),
        point1_xml_rd=" ".join(map(str, point1_rd_back.coords)),
        point2_wgs84=point2_wgs84,  # How data from PointField is returned
        point2_ewkt=point2_wgs84.ewkt,
        point2_geojson=_get_geojson(point2_wgs84.json),
        point2_xml_wgs84=" ".join(map(str, point2_wgs84.coords)),
    )


@pytest.fixture()
def city() -> City:
    return City.objects.create(name="CloudCity", region="OurRegion")


@pytest.fixture()
def restaurant(city) -> Restaurant:
    return Restaurant.objects.create(
        name="Café Noir",
        city=city,
        location=CoordinateInputs.point1_rd,
        rating=5.0,
        is_open=True,
        tags=["cafe", "black"],
    )


@pytest.fixture()
def restaurant_m2m(restaurant) -> Restaurant:
    restaurant.opening_hours.add(
        OpeningHour.objects.create(weekday=calendar.FRIDAY),
        OpeningHour.objects.create(weekday=calendar.SATURDAY),
        OpeningHour.objects.create(weekday=calendar.SUNDAY, start_time=time(20, 0)),
    )
    return restaurant


@pytest.fixture()
def bad_restaurant() -> Restaurant:
    return Restaurant.objects.create(
        name="Foo Bar",
        location=CoordinateInputs.point2_rd,
        rating=1.0,
        is_open=False,
        created=current_datetime() + timedelta(hours=8),
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
