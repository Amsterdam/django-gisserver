import pytest
from django.core.exceptions import ValidationError

from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.fes20 import Filter
from gisserver.types import XsdTypes
from tests.gisserver.parsers.fes20.utils import compile_query


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
        "<fes:PropertyIsLessThan> should have 2 child nodes, got only 1. "
        "Allowed types are: <fes:Add>, <fes:Div>, <fes:Function>, <fes:Literal>, <fes:Mul>,"
        " <fes:Sub>, <fes:ValueReference>."
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
        "<fes:And> should have 2 child nodes, got only 1. Allowed types are: "
        "<fes:And>, <fes:BBOX>, <fes:Beyond>, <fes:Contains>, <fes:Crosses>, "
        "<fes:DWithin>, <fes:Disjoint>, <fes:Equals>, <fes:Intersects>, <fes:Not>, "
        "<fes:Or>, <fes:Overlaps>, <fes:PropertyIsBetween>, <fes:PropertyIsEqualTo>, "
        "<fes:PropertyIsGreaterThan>, <fes:PropertyIsGreaterThanOrEqualTo>, "
        "<fes:PropertyIsLessThan>, <fes:PropertyIsLessThanOrEqualTo>, "
        "<fes:PropertyIsLike>, <fes:PropertyIsNil>, <fes:PropertyIsNotEqualTo>, "
        "<fes:PropertyIsNull>, <fes:Touches>, <fes:Within>."
    )


def test_invalid_children():
    """See that get_tag_names() walks through the class hierarchy to
    provide all possible tag names.
    """
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <fes:PropertyIsLessThan>
                <fes:Filter></fes:Filter>
                <fes:SortBy></fes:SortBy>
            </fes:PropertyIsLessThan>
        </fes:Filter>
    """.strip()

    with pytest.raises(ExternalParsingError) as e:
        Filter.from_string(xml_text)

    assert str(e.value) == (
        "<fes:PropertyIsLessThan> does not support a <fes:Filter> child node. Allowed "
        "types are: <fes:Add>, <fes:Div>, <fes:Function>, <fes:Literal>, <fes:Mul>, "
        "<fes:Sub>, <fes:ValueReference>."
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


def test_compare_invalid_date_types():
    """Test that comparing invalid types is detected early."""
    xml_text = """
        <Filter>
            <PropertyIsEqualTo>
                <ValueReference>DateProperty</ValueReference>
                <Literal>100</Literal>
            </PropertyIsEqualTo>
        </Filter>
    """.strip()
    result = Filter.from_string(xml_text)

    # Test SQL generating
    with pytest.raises(
        ValidationError,
        match="Invalid data for the 'DateProperty' property: Date must be in YYYY-MM-DD HH:MM",
    ):
        compile_query(result, field_types={"DateProperty": XsdTypes.dateTime})


def test_compare_invalid_time_types():
    """Test that comparing invalid types is detected early."""
    xml_text = """
        <Filter>
            <PropertyIsEqualTo>
                <ValueReference>TimeProperty</ValueReference>
                <Literal>100</Literal>
            </PropertyIsEqualTo>
        </Filter>
    """.strip()
    result = Filter.from_string(xml_text)

    # Test SQL generating
    with pytest.raises(
        ValidationError,
        match="Invalid data for the 'TimeProperty' property: Time must be in HH:MM",
    ):
        compile_query(result, field_types={"TimeProperty": XsdTypes.time})
