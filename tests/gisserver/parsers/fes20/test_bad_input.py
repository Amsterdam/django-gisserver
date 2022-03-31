import pytest

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers import Filter


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
        "<{http://www.opengis.net/fes/2.0}PropertyIsLessThan> should have 2 child "
        "nodes, got 1 (possible tags: Add, Div, Function, Literal, Mul, Sub, ValueReference)"
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

    with pytest.raises(ExternalParsingError) as e:
        Filter.from_string(xml_text)

    assert str(e.value) == (
        "{http://www.opengis.net/fes/2.0}UpperBoundary should have 1 expression child node"
    )
