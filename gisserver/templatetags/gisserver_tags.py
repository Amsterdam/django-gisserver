from urllib.parse import urljoin

from django.template import Library

register = Library()


@register.filter(name="urljoin")
def urljoin_(fragment, server_url):
    return urljoin(server_url, fragment)
