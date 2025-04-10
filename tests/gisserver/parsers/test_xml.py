import pytest

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.xml import NSElement, parse_qname, parse_xml_from_string, split_ns, xmlns


class TestParseQName:
    """Prove that namespace aliases can be resolved"""

    def test_alias(self):
        xml_name = parse_qname("ns0:Point", ns_aliases={"ns0": "http://www.opengis.net/gml/3.2"})
        assert xml_name == "{http://www.opengis.net/gml/3.2}Point"

    def test_missing(self):
        with pytest.raises(ExternalParsingError, match="an XML namespace declaration is missing"):
            parse_qname("gml:Point", ns_aliases={"ns0": "http://www.opengis.net/gml/3.2"})

    def test_default_alias(self):
        xml_name = parse_qname("Point", ns_aliases={"": "http://www.opengis.net/gml/3.2"})
        assert xml_name == "{http://www.opengis.net/gml/3.2}Point"

    def test_attribute(self):
        xml_name = parse_qname("@gml:id", ns_aliases={"gml": "http://www.opengis.net/gml/3.2"})
        assert xml_name == "@{http://www.opengis.net/gml/3.2}id"

    def test_attribute_default_ns(self):
        xml_name = parse_qname("@id", ns_aliases={"": "http://www.opengis.net/gml/3.2"})
        assert xml_name == "@{http://www.opengis.net/gml/3.2}id"


def test_split_ns():
    """Prove that xml names can be properly splitted into their namespace and localname"""
    ns, localname = split_ns("{http://www.opengis.net/gml/3.2}Point")
    assert ns == "http://www.opengis.net/gml/3.2"
    assert localname == "Point"


class TestXmlNS:
    """Prove that the 'xmlns' enum works as advertised."""

    def test_as_namespaces(self):
        """Test that the common aliases work."""
        namespaces = xmlns.as_namespaces()
        assert namespaces["http://www.opengis.net/gml/3.2"] == "gml"
        assert namespaces["http://www.opengis.net/wfs/2.0"] == "wfs"
        assert namespaces["http://www.opengis.net/ows/1.1"] == "ows"

    def test_as_ns_aliases(self):
        ns_aliases = xmlns.as_ns_aliases()
        assert ns_aliases["gml"] == "http://www.opengis.net/gml/3.2"
        assert ns_aliases["ows"] == "http://www.opengis.net/ows/1.1"
        assert ns_aliases["gml"] == "http://www.opengis.net/gml/3.2"

    def test_qname(self):
        assert xmlns.gml32.qname("Point") == "{http://www.opengis.net/gml/3.2}Point"

    def test_contains(self):
        assert "{http://www.opengis.net/gml/3.2}Point" in xmlns.gml32


class TestParser:
    """Prove that the parser works and detects namespaces"""

    def test_bad_input(self):
        with pytest.raises(ExternalParsingError):
            parse_xml_from_string("<ns0:Point")

    def test_ns_aliases_single(self):
        """Prove that namespace declarations are tracked."""
        element = parse_xml_from_string(
            '<ns0:Point xmlns:ns0="http://www.opengis.net/gml/3.2"></ns0:Point>'
        )
        assert isinstance(element, NSElement)
        assert element.tag == "{http://www.opengis.net/gml/3.2}Point"
        assert element.ns_aliases == {"ns0": "http://www.opengis.net/gml/3.2"}

    def test_ns_aliases_depth(self):
        """Prove how stacked namespace declarations are properly tracked."""
        root = parse_xml_from_string(
            "<root>"
            '  <ns0:member xmlns:ns0="http://www.opengis.net/wfs/2.0"'
            '              xmlns:ows="http://www.opengis.net/ows/1.1">'
            '    <ns0:Point xmlns:ns0="http://www.opengis.net/gml/3.2">'  # redefined ns0!
            '      <pos srsDimension="2" xmlns="http://www.opengis.net/gml/3.2">1 2</pos>'  # default!
            "    </ns0:Point>"
            "  </ns0:member>"
            "</root>"
        )
        assert isinstance(root, NSElement)
        assert root.tag == "root"
        assert root.ns_aliases == {}

        member = root[0]
        assert member.tag == "{http://www.opengis.net/wfs/2.0}member"
        assert member.ns_aliases == {
            "ns0": "http://www.opengis.net/wfs/2.0",
            "ows": "http://www.opengis.net/ows/1.1",
        }

        point = member[0]
        assert isinstance(point, NSElement)
        assert point.tag == "{http://www.opengis.net/gml/3.2}Point"
        assert point.ns_aliases == {
            "ns0": "http://www.opengis.net/gml/3.2",  # replaced
            "ows": "http://www.opengis.net/ows/1.1",
        }

        pos = point[0]
        assert isinstance(pos, NSElement)
        assert pos.tag == "{http://www.opengis.net/gml/3.2}pos"
        assert pos.ns_aliases == {
            "ns0": "http://www.opengis.net/gml/3.2",
            "ows": "http://www.opengis.net/ows/1.1",
            "": "http://www.opengis.net/gml/3.2",  # xmlns without prefix
        }
