from urllib.parse import urljoin

from django.template import Library

from gisserver.output.utils import to_qname

register = Library()


@register.filter(name="urljoin")
def urljoin_(fragment, server_url):
    return urljoin(server_url, fragment)


@register.filter(name="to_qname")
def _to_qname(value):
    """Translate a full XML name to a shortened name, using common prefixes.."""
    return to_qname(value.namespace, value.name, {})
