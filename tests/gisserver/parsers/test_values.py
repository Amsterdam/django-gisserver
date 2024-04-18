from datetime import datetime, timezone

from gisserver.parsers.values import auto_cast, parse_iso_datetime


def test_auto_cast():
    assert auto_cast("1") == 1
    assert auto_cast("1.0") == 1.0
    assert auto_cast("2020-07-12T22:52:14.305Z") == datetime(
        2020, 7, 12, 22, 52, 14, 305000, tzinfo=timezone.utc
    )


def test_parse_iso_datetime():
    assert parse_iso_datetime("2020-07-12T22:52:14.305Z") == datetime(
        2020, 7, 12, 22, 52, 14, 305000, tzinfo=timezone.utc
    )
