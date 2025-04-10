"""General utilities for outputting XML content"""

from datetime import date, datetime, time, timezone
from decimal import Decimal as D

from django.core.exceptions import ImproperlyConfigured

from gisserver.features import FeatureType
from gisserver.parsers.xml import xmlns

AUTO_STR = (int, float, D, date, time)

COMMON_NAMESPACES = xmlns.as_namespaces()


__all__ = (
    "attr_escape",
    "build_feature_prefixes",
    "build_feature_qnames",
    "tag_escape",
    "to_qname",
    "render_xmlns_attributes",
    "value_to_text",
    "value_to_xml_string",
)


def tag_escape(s: str):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def attr_escape(s: str):
    # Slightly faster then html.escape() as it doesn't replace single quotes.
    # Having tried all possible variants, this code still outperforms other forms of escaping.
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def value_to_xml_string(value):
    # Simple scalar value
    if isinstance(value, str):  # most cases
        return tag_escape(value)
    elif isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, AUTO_STR):
        return value  # no need for _tag_escape(), and f"{value}" works faster.
    else:
        return tag_escape(str(value))


def value_to_text(value):
    # Simple scalar value, no XML escapes
    if isinstance(value, str):  # most cases
        return value
    elif isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    elif isinstance(value, bool):
        return "true" if value else "false"
    else:
        return value  # f"{value} works faster and produces the right format.


def render_xmlns_attributes(app_namespaces: dict[str, str]):
    """Render XML Namespace declaration attributes"""
    return " ".join(
        f'xmlns:{prefix}="{xml_namespace}"' if prefix else f'xmlns="{xml_namespace}"'
        for xml_namespace, prefix in app_namespaces.items()
    )


def build_feature_qnames(
    feature_types: list[FeatureType], app_namespaces: dict[str, str]
) -> dict[FeatureType, str]:
    """Build a list for short XML names."""
    return {
        feature_type: to_qname(feature_type.xml_namespace, feature_type.name, app_namespaces)
        for feature_type in feature_types
    }


def build_feature_prefixes(
    feature_types: list[FeatureType], app_namespaces: dict[str, str]
) -> dict[FeatureType, str]:
    """Make a list of feature types mapped to XML prefixes."""
    return {
        feature_type: app_namespaces[feature_type.xml_namespace] for feature_type in feature_types
    }


def to_qname(namespace, localname, namespaces: dict[str, str]) -> str:
    """Convert a fully qualified XML tag name to a prefixed short name."""
    if namespace is None:
        return localname

    prefix = namespaces.get(namespace)  # allow ""
    if prefix is None:
        try:
            prefix = COMMON_NAMESPACES[namespace]
        except KeyError:
            raise ImproperlyConfigured(
                f"No XML namespace prefix defined in WFSView for {namespace}"
            ) from None

    return f"{prefix}:{localname}" if prefix else localname
