"""Prove that GET request parameters can be properly parsed."""

import pytest
from django.http import QueryDict

from gisserver.exceptions import (
    InvalidParameterValue,
    MissingParameterValue,
    OperationParsingFailed,
)
from gisserver.parsers.ows import KVPRequest
from gisserver.parsers.ows.kvp import parse_kvp_namespaces


class TestKVPRequest:
    """Prove the Key-Value-Pair GET request syntax is properly parsed.
    This translates query string data into basic Python types.
    """

    def test_get_values(self):
        """Prove retrieving values can cast data"""
        kvp = KVPRequest(
            QueryDict("SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&COUNT=1&TYPENAMES=aa,bb")
        )
        assert kvp.get_str("request") == "GetFeature"
        assert kvp.get_int("count") == 1
        assert kvp.get_list("typeNames") == ["aa", "bb"]

    def test_missing_value(self):
        """Prove missing values are properly reported"""
        kvp = KVPRequest(QueryDict("SERVICE=WFS"))
        with pytest.raises(MissingParameterValue) as exc_info:
            kvp.get_str("request")

        assert exc_info.value.locator == "request"

    def test_missing_default(self):
        """Prove missing values are properly reported"""
        kvp = KVPRequest(QueryDict("SERVICE=WFS&TYPENAMES="))
        assert kvp.get_str("request", default="foo") == "foo"
        assert kvp.get_str("request", default=None) is None
        assert kvp.get_list("typenames", default=None) is None  # exists but empty

    def test_empty_value(self):
        """Prove empty values are properly reported."""
        kvp = KVPRequest(QueryDict("SERVICE=WFS&REQUEST="))
        with pytest.raises(InvalidParameterValue) as exc_info:
            kvp.get_str("request")

        assert exc_info.value.locator == "request"

    def test_non_int_value(self):
        """Prove type parsing errors are properly reported."""
        kvp = KVPRequest(QueryDict("COUNT=foo"))
        with pytest.raises(InvalidParameterValue, match="Invalid COUNT argument: ") as exc_info:
            kvp.get_int("count")
        assert exc_info.value.locator == "count"

    def test_parse_pairs(self):
        """Prove splitting syntax works."""
        kvp = KVPRequest(
            QueryDict(
                "TYPENAMES=(ns1:F1,ns2:F2)(ns1:F1,ns1:F1)"
                "&ALIASES=(A,B)(C,D)"
                "&FILTER=(<Filter>… for A,B …</Filter>)(<Filter>… for C,D …</Filter>)"
                "&BBOX=11,22,33,44"
            )
        )
        sub_requests = kvp.split_parameter_lists()
        assert sub_requests[0].get_list("aliases") == ["A", "B"]
        assert sub_requests[0].get_str("filter") == "<Filter>… for A,B …</Filter>"
        assert sub_requests[0].get_str("bbox") == "11,22,33,44"  # still allowed shared parameters

        assert sub_requests[1].get_list("aliases") == ["C", "D"]
        assert sub_requests[1].get_str("filter") == "<Filter>… for C,D …</Filter>"
        assert sub_requests[1].get_str("bbox") == "11,22,33,44"

    def test_parse_pairs_no_pairs(self):
        """Prove splitting syntax ignores ."""
        kvp = KVPRequest(QueryDict("TYPENAMES=ns1:F1,ns2:F2&ALIASES=A,B"))
        sub_requests = kvp.split_parameter_lists()
        assert sub_requests == [kvp]

    def test_parse_pairs_unbalanced(self):
        """Prove splitting syntax tests for unbalanced pairs."""
        kvp = KVPRequest(QueryDict("TYPENAMES=(ns1:F1,ns2:F2)(ns1:F1,ns1:F1)&ALIASES=(A,B)"))

        with pytest.raises(
            OperationParsingFailed, match="Inconsistent pairs between: ALIASES, TYPENAMES"
        ):
            kvp.split_parameter_lists()

    def test_parse_resolve_namespace(self):
        """Prove namespaces are properly resolved."""
        kvp = KVPRequest(
            QueryDict(
                "TYPENAMES=app:F1,ns2:F2"
                "&NAMESPACES=xmlns(app,http://example.org/gisserver),xmlns(ns2,http://other.org/)"
            )
        )
        assert kvp.ns_aliases["app"] == "http://example.org/gisserver"
        assert kvp.ns_aliases["ns2"] == "http://other.org/"

        type_names = kvp.get_list("typeNames")
        assert type_names == ["app:F1", "ns2:F2"]

        resolved_type_names = [kvp.parse_qname(v) for v in type_names]
        assert resolved_type_names == ["{http://example.org/gisserver}F1", "{http://other.org/}F2"]

    def test_parse_resolve_default_namespace(self):
        """Prove namespaces are properly resolved."""
        kvp = KVPRequest(
            QueryDict(
                "TYPENAMES=F1,ns2:F2"
                "&NAMESPACES=xmlns(http://example.org/gisserver),xmlns(ns2,http://other.org/)"
            )
        )
        assert kvp.ns_aliases[""] == "http://example.org/gisserver"
        assert kvp.ns_aliases["ns2"] == "http://other.org/"

        type_names = kvp.get_list("typeNames")
        assert type_names == ["F1", "ns2:F2"]

        resolved_type_names = [kvp.parse_qname(v) for v in type_names]
        assert resolved_type_names == [
            "{http://example.org/gisserver}F1",
            "{http://other.org/}F2",
        ]


class TestParseKVPNamespaces:
    """Prove that parsing the NAMESPACES parameter works as expected."""

    def test_aliases(self):
        ns_aliases = parse_kvp_namespaces(
            "xmlns(app,http://example.org/),xmlns(ns2,http://other.org/)"
        )
        assert ns_aliases == {
            "app": "http://example.org/",
            "ns2": "http://other.org/",
        }

    def test_default_alias(self):
        ns_aliases = parse_kvp_namespaces(
            "xmlns(http://example.org/),xmlns(ns2,http://other.org/)"
        )
        assert ns_aliases == {
            "": "http://example.org/",
            "ns2": "http://other.org/",
        }

    @pytest.mark.parametrize(
        "value",
        [
            "xmlns(http://example.org/",
            "xmlns(foo,bar),more",
            "foobar",
            "foo,xmlns(x,y)",
        ],
    )
    def test_syntax_errors(self, value):
        with pytest.raises(InvalidParameterValue, match=r"Expected xmlns\("):
            parse_kvp_namespaces(value)
