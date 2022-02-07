import re
from datetime import datetime
from decimal import Decimal as D

from django.utils.dateparse import parse_datetime

from gisserver.exceptions import ExternalParsingError

RE_FLOAT = re.compile(r"\A[0-9]+(\.[0-9]+)\Z")


def auto_cast(value: str):
    """Automatically cast a value to a scalar."""
    if value.isdigit():
        return int(value)
    elif RE_FLOAT.match(value):
        return D(value)
    elif "T" in value:
        try:
            return parse_iso_datetime(value)
        except ValueError:
            pass

    return value


def parse_iso_datetime(raw_value: str) -> datetime:
    value = parse_datetime(raw_value)
    if value is None:
        raise ExternalParsingError(
            "Date must be in YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format."
        )
    return value


def parse_bool(raw_value: str):
    if raw_value in ("true", "1"):
        return True
    elif raw_value in ("false", "0"):
        return False
    else:
        raise ExternalParsingError(f"Can't cast '{raw_value}' to boolean")
