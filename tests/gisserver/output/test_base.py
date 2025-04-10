import pytest
from django.core.exceptions import ImproperlyConfigured

from gisserver.output.base import to_qname


def test_to_qname():
    """Prove XML aliases are properly rendered."""
    assert to_qname("http://example.org", "test", {"http://example.org": "ns0"}) == "ns0:test"
    assert to_qname("http://example.org", "test", {"http://example.org": ""}) == "test"

    with pytest.raises(ImproperlyConfigured):
        assert to_qname("http://example.com/foo", "test", {"http://example.org": "ns0"})
