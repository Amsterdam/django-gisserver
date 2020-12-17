import pytest

from gisserver.parsers.fes20.query import FesBeyondLookup  # noqa
from tests.test_gisserver.models import Restaurant


@pytest.mark.django_db
def test_beyond_lookup(restaurant, bad_restaurant):
    # No SRID is defined for the 'location', so only WFS84 degrees can be used.
    distance = 0.0001

    qs = Restaurant.objects.filter(location__dwithin=(restaurant.location, distance))
    assert list(qs) == [restaurant]

    qs = Restaurant.objects.filter(location__fes_beyond=(restaurant.location, distance))
    assert list(qs) == [bad_restaurant]
