from pathlib import Path

import pytest
from django.contrib.gis.geos import Point

from tests.test_gisserver.models import Restaurant

HERE = Path(__file__).parent
SRID_RD_NEW = 28992


@pytest.fixture()
def restaurant() -> Restaurant:
    return Restaurant.objects.create(
        name="Café Noir", location=Point(122411, 486250, srid=SRID_RD_NEW)
    )
