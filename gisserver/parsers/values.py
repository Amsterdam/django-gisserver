import logging
import re
from datetime import datetime
from decimal import Decimal as D

from django.utils.dateparse import parse_datetime

from gisserver.exceptions import ExternalParsingError

logger = logging.getLogger(__name__)
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
        raise ExternalParsingError("Date must be in YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format.")
    return value


def parse_bool(raw_value: str):
    if raw_value in ("true", "1"):
        return True
    elif raw_value in ("false", "0"):
        return False
    else:
        raise ExternalParsingError(f"Can't cast '{raw_value}' to boolean")


def fix_type_name(type_name: str, feature_namespace: str):
    """Fix the XML namespace for a typename value.

    When the default namespace points to the "wfs" or "gml" namespaces,
    parsing the QName of the type value will resolve that element as existing there.
    This will correct such error, and restore the feature-type namespace.
    """
    if feature_namespace[0] == "{":
        raise ValueError("Incorrect namespace argument")

    alt_type_name = type_name
    if type_name.startswith("{http://www.opengis.net/"):
        # When the XML POST request used xmlns="http://www.opengis.net/wfs/2.0",
        # this will define a default namespace that all QName values resolve to.
        # As this is not detectable at the moment of parsing, correct it here.
        alt_type_name = f"{{{feature_namespace}}}{type_name[type_name.index('}')+1:]}"
        logger.debug("Corrected namespaced '%s' to '%s'", type_name, alt_type_name)
    elif type_name[0] != "{":
        # Typically happens in GET requests, or when no namespace prefix is used in XML POST
        alt_type_name = f"{{{feature_namespace}}}{type_name}"
        logger.debug("Corrected unnamespaced '%s' to namespaced '%s'", type_name, alt_type_name)
    return alt_type_name
