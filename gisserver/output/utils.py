"""General utilities for outputting XML content"""

from datetime import date, datetime, time, timezone
from decimal import Decimal as D

from django.core.exceptions import ImproperlyConfigured

from gisserver.parsers.xml import xmlns

AUTO_STR = (int, float, D, date, time)

COMMON_NAMESPACES = xmlns.as_namespaces()


__all__ = (
    "attr_escape",
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


def render_xmlns_attributes(xml_namespaces: dict[str, str]):
    """Render XML Namespace declaration attributes"""
    return " ".join(
        f'xmlns:{prefix}="{xml_namespace}"' if prefix else f'xmlns="{xml_namespace}"'
        for xml_namespace, prefix in xml_namespaces.items()
    )


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
