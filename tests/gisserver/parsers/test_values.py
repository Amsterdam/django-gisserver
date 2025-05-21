from datetime import date, datetime, time, timedelta, timezone

import pytest

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.values import (
    auto_cast,
    parse_iso_date,
    parse_iso_datetime,
    parse_iso_duration,
    parse_iso_time,
)


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


def test_parse_iso_date():
    assert parse_iso_date("2020-07-12") == date(2020, 7, 12)


def test_parse_iso_time():
    assert parse_iso_time("11:34") == time(11, 34)


def test_parse_iso_duration():
    assert parse_iso_duration("PT1H") == timedelta(hours=1)


def test_parse_invalid_datetime():
    with pytest.raises(ExternalParsingError, match="must be in YYYY-MM-DD"):
        parse_iso_datetime("2020-07-123")

    with pytest.raises(ExternalParsingError, match="month must be in 1..12"):
        parse_iso_datetime("2020-30-01T22:52:14")


def test_parse_invalid_date():
    with pytest.raises(ExternalParsingError, match="must be in YYYY-MM-DD format"):
        parse_iso_date("2020-07")

    with pytest.raises(ExternalParsingError, match="month must be in 1..12"):
        parse_iso_date("2020-30-01")


def test_parse_invalid_time():
    with pytest.raises(ExternalParsingError, match="must be in HH:MM"):
        parse_iso_time("foobar")

    with pytest.raises(ExternalParsingError, match="hour must be in 0..23"):
        parse_iso_time("34:23")


def test_parse_invalid_duration():
    with pytest.raises(ExternalParsingError, match="ISO"):
        parse_iso_duration("1 day, 11:23")
