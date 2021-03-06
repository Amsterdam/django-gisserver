from datetime import timedelta

from pathlib import Path
import ctypes

import django
import pytest
from django.contrib.gis.gdal import gdal_full_version, gdal_version
from django.contrib.gis.geos import Point, geos_version
from django.db import connection

from gisserver import conf
from tests.constants import RD_NEW_PROJ, RD_NEW_SRID, RD_NEW_WKT
from tests.test_gisserver.models import City, Restaurant, current_datetime
from tests.xsd_download import download_schema

HERE = Path(__file__).parent
XSD_ROOT = HERE.joinpath("files/xsd")


def pytest_configure():
    try:
        gdal_ver = gdal_full_version().decode()
    except ctypes.ArgumentError:
        # gdal_full_version() is broken in Django<3.1,
        # see https://code.djangoproject.com/ticket/31292
        gdal_ver = gdal_version().decode()

    geos_ver = geos_version().decode()
    print(
        f'Running with Django {django.__version__}, GDAL="{gdal_ver}" GEOS="{geos_ver}"'
    )
    print(f"Using GISSERVER_USE_DB_RENDERING={conf.GISSERVER_USE_DB_RENDERING}")

    for url in (
        "http://schemas.opengis.net/wfs/2.0/wfs.xsd",
        "http://schemas.opengis.net/gml/3.2.1/gml.xsd",
    ):
        if not XSD_ROOT.joinpath(url.replace("http://", "")).exists():
            print(f"Caching {url} to {XSD_ROOT.absolute()}")
            download_schema(url)


@pytest.fixture()
def city() -> City:
    return City.objects.create(name="CloudCity")


@pytest.fixture()
def restaurant(city) -> Restaurant:
    return Restaurant.objects.create(
        name="Café Noir",
        city=city,
        location=Point(122411, 486250, srid=RD_NEW_SRID),
        rating=5.0,
        is_open=True,
    )


@pytest.fixture()
def bad_restaurant() -> Restaurant:
    return Restaurant.objects.create(
        name="Foo Bar",
        location=Point(122421, 486290, srid=RD_NEW_SRID),
        rating=1.0,
        is_open=False,
        created=current_datetime() + timedelta(hours=8),
    )


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Make sure PostGIS uses the same coordinate transformation as Django will.

    This is a fix for Travis CI, which uses an older GDAL / proj version.
    """
    # Homebrew uses at the time of writing this code:
    # - libproj.15 (version 17.1.0)
    # - libgeos 13.2.0
    #
    # Revealed using:
    #
    # objdump -x /usr/local/Cellar/postgresql/*/lib/postgresql/postgis-2.5.so
    # cat /usr/local/Cellar/postgresql/*/share/postgresql/extension/postgis--2.5.3.sql
    #
    # SELECT postgis_full_version() -- shows on homebrew:
    #
    # POSTGIS="2.5.3 r17699" [EXTENSION]
    # PGSQL="110"
    # GEOS="3.8.0-CAPI-1.13.1 "
    # PROJ="Rel. 6.3.0, January 1st, 2020"
    # GDAL="GDAL 2.4.2, released 2019/06/28"
    # LIBXML="2.9.9"
    # LIBJSON="0.13.1"
    # LIBPROTOBUF="1.3.2"
    # RASTER
    with django_db_blocker.unblock():
        with connection.cursor() as c:
            # Show the postgis version for debugging
            c.callproc("postgis_full_version")  # SELECT postgis_full_version()
            result = c.fetchone()[0]
            print(f"Postgresql setup: {result}")

            # Install the latest PROJ.4 definition for RD/NEW
            c.execute(
                "UPDATE spatial_ref_sys SET proj4text=%s, srtext=%s WHERE srid=%s",
                [RD_NEW_PROJ, RD_NEW_WKT, RD_NEW_SRID],
            )
