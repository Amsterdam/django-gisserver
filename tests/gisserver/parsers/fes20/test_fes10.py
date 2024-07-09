"""Additional tests for FES 1.0 Arithmetic operators."""

import pytest
from django.db import models
from django.db.models import Q, Value

from gisserver.parsers.fes20 import Filter
from gisserver.parsers.fes20.expressions import (
    BinaryOperator,
    BinaryOperatorType,
    Literal,
    ValueReference,
)

# Importing all these elements directly, so copy-paste from assertion errors works:
from gisserver.parsers.fes20.operators import (
    BinaryComparisonName,
    BinaryComparisonOperator,
    MatchAction,
)
from gisserver.parsers.fes20.query import CompiledQuery


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
    query = result.compile_query()
    integer_field = models.IntegerField()
    assert query == CompiledQuery(
        lookups=[
            Q(
                SomeProperty__exact=(
                    Value(100, output_field=integer_field)
                    - Value(50, output_field=integer_field)
                    + Value(200, output_field=integer_field)
                )
            )
        ]
    ), repr(query)


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
