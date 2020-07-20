from gisserver.types import parse_iso_datetime


def test_parse_iso_datetime():
    assert parse_iso_datetime("2020-07-12T22:52:14.305Z")
