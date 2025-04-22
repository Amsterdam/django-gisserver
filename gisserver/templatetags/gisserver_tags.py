from __future__ import annotations

from urllib.parse import urljoin

from django.template import Library

from gisserver.features import FeatureType
from gisserver.output import to_qname
from gisserver.types import XsdAnyType, XsdNode

register = Library()


@register.filter(name="urljoin")
def urljoin_(fragment, server_url):
    return urljoin(server_url, fragment)


@register.filter(name="to_qname")
def _to_qname(xsd_type: XsdNode | XsdAnyType, xml_namespaces=None):
    """Translate a full XML name to a shortened name, using common prefixes.."""
    return to_qname(xsd_type.namespace, xsd_type.name, xml_namespaces or {})


@register.simple_tag(name="feature_qname", takes_context=True)
def feature_qname(context, feature_type: FeatureType, xml_namespaces=None):
    """Translate a full XML name to a shortened name."""
    if xml_namespaces is None:
        xml_namespaces = context["xml_namespaces"]
    return to_qname(feature_type.xml_namespace, feature_type.name, xml_namespaces)
