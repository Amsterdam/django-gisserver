import pytest

from gisserver.exceptions import ExternalParsingError
from gisserver.types import GmlElement, XsdComplexType, XsdElement, XsdTypes


class TestXsdElements:
    """Prove the internal XML schema definition logic works."""

    def test_no_namespace(self):
        element = XsdElement("age", type=XsdTypes.integer, namespace=None)
        assert element.xml_name == "age"

    def test_gml_default(self):
        element = GmlElement("age", type=XsdTypes.integer, namespace=None)
        assert element.xml_name == "age"

    def test_default_alias(self):
        """Prove that the namespace aliases properly work."""
        namespace = "https://example.org/app"
        element = XsdElement(
            "age",
            type=XsdTypes.integer,
            namespace=namespace,
        )
        assert element.xml_name == "{https://example.org/app}age"

    def test_resolve_element_path(self):
        """Test how the XSD element resolving works.

        This resolving logic is central to translating request XML paths
        into our internal XML schema definition, and therefore the ORM paths.

        This also tests it can properly recognize namespaces.
        """
        namespace = "https://example.org/app"
        person_type = XsdComplexType(
            "PersonType",
            namespace=namespace,
            elements=[
                XsdElement(
                    "name",
                    type=XsdTypes.string,
                    namespace=namespace,
                ),
                XsdElement("age", type=XsdTypes.integer, namespace=namespace),
            ],
        )

        house_type = XsdComplexType(
            "HouseType",
            namespace=namespace,
            elements=[
                XsdElement("owner", type=person_type, namespace=namespace),
            ],
        )

        # Test resolving an element
        path = house_type.resolve_element_path("app:owner/app:name", {"app": namespace})
        assert path is not None
        assert len(path) == 2
        assert [e.xml_name for e in path] == [
            "{https://example.org/app}owner",
            "{https://example.org/app}name",
        ]
        assert path[-1].name == "name"
        assert path[-1].type == XsdTypes.string

        # Also test with a different namespace mapping.
        path = house_type.resolve_element_path("ns0:owner/ns0:age", {"ns0": namespace})
        assert path is not None
        assert len(path) == 2
        assert path[-1].name == "age"
        assert path[-1].type == XsdTypes.integer

        # Test when not finding results
        for xpath in ("app:owner/app:name/app:something", "app:foobar", "app:foo/app:bar"):
            path = house_type.resolve_element_path(xpath, {"app": namespace})
            assert path is None

        # Test when namespace declaration is missing
        with pytest.raises(
            ExternalParsingError,
            match="Can't resolve QName 'foo:owner', an XML namespace declaration is missing.",
        ):
            house_type.resolve_element_path("foo:owner/foo:name", ns_aliases={})
        assert path is None
