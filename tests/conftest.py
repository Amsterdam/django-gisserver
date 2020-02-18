from pathlib import Path

import django
import pytest
from django.contrib.gis.geos import Point, geos_version
from django.contrib.gis.gdal import gdal_version

from tests.test_gisserver.models import Restaurant

HERE = Path(__file__).parent
SRID_RD_NEW = 28992


def pytest_configure():
    gdal_ver = gdal_version().decode()
    geos_ver = geos_version().decode()
    print(
        f'Running with Django {django.__version__}, GDAL="{gdal_ver}" GEOS="{geos_ver}"'
    )


@pytest.fixture()
def restaurant() -> Restaurant:
    return Restaurant.objects.create(
        name="Café Noir", location=Point(122411, 486250, srid=SRID_RD_NEW)
    )
