"""Additional tests for FES 1.0 Arithmetic operators."""

import pytest
from django.core.exceptions import ValidationError
from django.db.models import F, Q

# Importing all these elements directly, so copy-paste from assertion errors works:
from gisserver.parsers.fes20 import (
    BinaryComparisonName,
    BinaryComparisonOperator,
    BinaryOperator,
    BinaryOperatorType,
    Filter,
    Literal,
    MatchAction,
    ValueReference,
)
from gisserver.parsers.query import CompiledQuery
from gisserver.types import XsdTypes

from .utils import compile_query


def test_fes10_add_sub():
    """A simple non-spatial filter checking to see if SomeProperty is equal to 100."""
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:PropertyName>SomeProperty</fes:PropertyName>
                <fes:Add>
                    <fes:Sub>
                        <fes:Literal>100</fes:Literal>
                        <fes:Literal>50</fes:Literal>
                    </fes:Sub>
                    <fes:Literal>200</fes:Literal>
                </fes:Add>
            </fes:PropertyIsEqualTo>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinaryComparisonOperator(
            operatorType=BinaryComparisonName.PropertyIsEqualTo,
            expression=(
                ValueReference(xpath="SomeProperty"),
                BinaryOperator(
                    _operatorType=BinaryOperatorType.Add,
                    expression=(
                        BinaryOperator(
                            _operatorType=BinaryOperatorType.Sub,
                            expression=(
                                Literal(raw_value="100"),
                                Literal(raw_value="50"),
                            ),
                        ),
                        Literal(raw_value="200"),
                    ),
                ),
            ),
            matchCase=True,
            matchAction=MatchAction.Any,
        )
    )
    result = Filter.from_string(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = compile_query(result)
    assert query == CompiledQuery(
        query.feature_types,
        lookups=[
            # calculation happens in BinaryOperator
            Q(SomeProperty__exact=250)
        ],
    ), repr(query)


def test_fes10_add_other_property():
    """A simple non-spatial filter checking to see if SomeProperty is equal to 100."""
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:PropertyName>SomeProperty</fes:PropertyName>
                <fes:Add>
                    <fes:ValueReference>OtherProperty</fes:ValueReference>
                    <fes:Literal>200</fes:Literal>
                </fes:Add>
            </fes:PropertyIsEqualTo>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinaryComparisonOperator(
            operatorType=BinaryComparisonName.PropertyIsEqualTo,
            expression=(
                ValueReference(xpath="SomeProperty"),
                BinaryOperator(
                    _operatorType=BinaryOperatorType.Add,
                    expression=(
                        ValueReference(xpath="OtherProperty"),
                        Literal(raw_value="200"),
                    ),
                ),
            ),
            matchCase=True,
            matchAction=MatchAction.Any,
        )
    )
    result = Filter.from_string(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    # Testing against repr() because CombinedExpression / Value doesn't do __eq__ testing.
    query = compile_query(result)
    expect = CompiledQuery(
        query.feature_types,
        lookups=[Q(SomeProperty__exact=F("OtherProperty") + 200)],
    )
    assert repr(query) == repr(expect), repr(query)


def test_fes10_reverse_operators():
    """A simple non-spatial filter checking to see if SomeProperty is equal to 100."""
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:PropertyName>SomeProperty</fes:PropertyName>
                <fes:Sub>
                    <fes:Literal>200</fes:Literal>
                    <fes:ValueReference>OtherProperty</fes:ValueReference>
                </fes:Sub>
            </fes:PropertyIsEqualTo>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinaryComparisonOperator(
            operatorType=BinaryComparisonName.PropertyIsEqualTo,
            expression=(
                ValueReference(xpath="SomeProperty"),
                BinaryOperator(
                    _operatorType=BinaryOperatorType.Sub,
                    expression=(
                        Literal(raw_value="200"),
                        ValueReference(xpath="OtherProperty"),
                    ),
                ),
            ),
            matchCase=True,
            matchAction=MatchAction.Any,
        )
    )
    result = Filter.from_string(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    # Testing against repr() because CombinedExpression / Value doesn't do __eq__ testing.
    query = compile_query(result)
    expect = CompiledQuery(
        query.feature_types,
        lookups=[Q(SomeProperty__exact=200 - F("OtherProperty"))],
    )
    assert repr(query) == repr(expect), repr(query)


def test_fes10_add_date_field():
    """A simple non-spatial filter checking to see if SomeProperty is equal to 100."""
    # Based on what QGis generated when typing: "DOCUMENT_DATE > 2020-01-01" in the filter.
    xml_text = """
        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
           <fes:PropertyIsGreaterThan>
            <fes:ValueReference>DOCUMENT_DATE</fes:ValueReference>
            <fes:Sub>
             <fes:Sub>
              <fes:Literal>2020</fes:Literal>
              <fes:Literal>1</fes:Literal>
             </fes:Sub>
             <fes:Literal>1</fes:Literal>
            </fes:Sub>
           </fes:PropertyIsGreaterThan>
         </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinaryComparisonOperator(
            operatorType=BinaryComparisonName.PropertyIsGreaterThan,
            expression=(
                ValueReference(xpath="DOCUMENT_DATE"),
                BinaryOperator(
                    _operatorType=BinaryOperatorType.Sub,
                    expression=(
                        BinaryOperator(
                            _operatorType=BinaryOperatorType.Sub,
                            expression=(
                                Literal(raw_value="2020"),
                                Literal(raw_value="1"),
                            ),
                        ),
                        Literal(raw_value="1"),
                    ),
                ),
            ),
            matchCase=True,
            matchAction=MatchAction.Any,
        )
    )
    result = Filter.from_string(xml_text)
    assert result == expected, f"result={result!r}"

    # Test early value comparisons
    with pytest.raises(
        ValidationError,
        match="Invalid data for the 'DOCUMENT_DATE' property: Can't cast '2018' to dateTime.",
    ):
        compile_query(result, field_types={"DOCUMENT_DATE": XsdTypes.dateTime})


@pytest.mark.parametrize("leading_whitespace", [1, 0])
def test_fes10_no_namespace(leading_whitespace):
    """Test that omitting a namespace still parses the object."""
    xml_text = """
        <Filter>
            <PropertyIsEqualTo>
                <ValueReference>SomeProperty</ValueReference>
                <Literal>100</Literal>
            </PropertyIsEqualTo>
        </Filter>
    """

    if leading_whitespace:
        xml_text = xml_text.strip()

    expected = Filter(
        predicate=BinaryComparisonOperator(
            operatorType=BinaryComparisonName.PropertyIsEqualTo,
            expression=(
                ValueReference(xpath="SomeProperty"),
                Literal(raw_value="100"),
            ),
            matchCase=True,
            matchAction=MatchAction.Any,
        )
    )
    result = Filter.from_string(xml_text)
    assert result == expected, f"result={result!r}"
