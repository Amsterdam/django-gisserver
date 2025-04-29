import pytest

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.fes20 import Filter


def test_unclosed_xml():
    """A simple non-spatial filter comparing a property value to a literal.
    In this case, the DEPTH is checked to find instances where it is less than
    30 - possibly to identify areas that need dredging.
    """
    xml_text = """
        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:PropertyIsBetween>
        </fes:Filter>
    """.strip()

    with pytest.raises(ExternalParsingError) as e:
        Filter.from_string(xml_text)

    assert str(e.value) == "mismatched tag: line 3, column 10"


def test_invalid_root():
    """A simple non-spatial filter comparing a property value to a literal.
    In this case, the DEPTH is checked to find instances where it is less than
    30 - possibly to identify areas that need dredging.
    """
    with pytest.raises(ExternalParsingError) as e:
        Filter.from_string("<FilterTest></FilterTest>")

    assert str(e.value) == (
        "Filter parser expects an <{http://www.opengis.net/fes/2.0}Filter> node,"
        " got <FilterTest>"
    )


def test_missing_children():
    """A simple non-spatial filter comparing a property value to a literal.
    In this case, the DEPTH is checked to find instances where it is less than
    30 - possibly to identify areas that need dredging.
    """
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsLessThan>
                <fes:Literal>30</fes:Literal>
            </fes:PropertyIsLessThan>
        </fes:Filter>
    """.strip()

    with pytest.raises(ExternalParsingError) as e:
        Filter.from_string(xml_text)

    assert str(e.value) == (
        "<{http://www.opengis.net/fes/2.0}PropertyIsLessThan> should have 2 child nodes, got 1 "
        "(possible tags:"
        " {http://www.opengis.net/fes/2.0}Add,"
        " {http://www.opengis.net/fes/2.0}Div,"
        " {http://www.opengis.net/fes/2.0}Function,"
        " {http://www.opengis.net/fes/2.0}Literal,"
        " {http://www.opengis.net/fes/2.0}Mul,"
        " {http://www.opengis.net/fes/2.0}Sub,"
        " {http://www.opengis.net/fes/2.0}ValueReference"
        ")"
    )


def test_missing_children_operator():
    """See that get_tag_names() walks through the class hierarchy to
    provide all possible tag names.
    """
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <fes:And>
                <fes:PropertyIsLessThan>
                    <fes:ValueReference>foobar</fes:ValueReference>
                    <fes:Literal>30</fes:Literal>
                </fes:PropertyIsLessThan>
            </fes:And>
        </fes:Filter>
    """.strip()

    with pytest.raises(ExternalParsingError) as e:
        Filter.from_string(xml_text)

    assert str(e.value) == (
        "<{http://www.opengis.net/fes/2.0}And> should have 2 child nodes, got 1 "
        "(possible tags: {http://www.opengis.net/fes/2.0}BBOX, "
        "{http://www.opengis.net/fes/2.0}Beyond, "
        "{http://www.opengis.net/fes/2.0}Contains, "
        "{http://www.opengis.net/fes/2.0}Crosses, "
        "{http://www.opengis.net/fes/2.0}DWithin, "
        "{http://www.opengis.net/fes/2.0}Disjoint, "
        "{http://www.opengis.net/fes/2.0}Equals, "
        "{http://www.opengis.net/fes/2.0}Intersects, "
        "{http://www.opengis.net/fes/2.0}Overlaps, "
        "{http://www.opengis.net/fes/2.0}PropertyIsBetween, "
        "{http://www.opengis.net/fes/2.0}PropertyIsEqualTo, "
        "{http://www.opengis.net/fes/2.0}PropertyIsGreaterThan, "
        "{http://www.opengis.net/fes/2.0}PropertyIsGreaterThanOrEqualTo, "
        "{http://www.opengis.net/fes/2.0}PropertyIsLessThan, "
        "{http://www.opengis.net/fes/2.0}PropertyIsLessThanOrEqualTo, "
        "{http://www.opengis.net/fes/2.0}PropertyIsLike, "
        "{http://www.opengis.net/fes/2.0}PropertyIsNil, "
        "{http://www.opengis.net/fes/2.0}PropertyIsNotEqualTo, "
        "{http://www.opengis.net/fes/2.0}PropertyIsNull, "
        "{http://www.opengis.net/fes/2.0}Touches, "
        "{http://www.opengis.net/fes/2.0}Within)"
    )


def test_between_fixed_ordering():
    """A simple non-spatial filter comparing a property value to a literal.
    In this case, the DEPTH is checked to find instances where it is less than
    30 - possibly to identify areas that need dredging.
    """
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsBetween>
                <fes:Literal>30</fes:Literal>
                <fes:Literal>30</fes:Literal>
                <fes:Literal>30</fes:Literal>
            </fes:PropertyIsBetween>
        </fes:Filter>
    """.strip()

    with pytest.raises(ExternalParsingError) as e:
        Filter.from_string(xml_text)

    assert str(e.value) == (
        "{http://www.opengis.net/fes/2.0}PropertyIsBetween should have 3 child nodes: "
        "(expression), <LowerBoundary>, <UpperBoundary>"
    )


def test_between_sub_elements():
    """A simple non-spatial filter comparing a property value to a literal.
    In this case, the DEPTH is checked to find instances where it is less than
    30 - possibly to identify areas that need dredging.
    """
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsBetween>
                <fes:ValueReference>field</fes:ValueReference>
                <fes:LowerBoundary><fes:Literal>30</fes:Literal></fes:LowerBoundary>
                <fes:UpperBoundary>30</fes:UpperBoundary>
            </fes:PropertyIsBetween>
        </fes:Filter>
    """.strip()

    with pytest.raises(
        ExternalParsingError,
        match="{http://www.opengis.net/fes/2.0}UpperBoundary should have 1 expression child node",
    ):
        Filter.from_string(xml_text)
