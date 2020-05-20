"""Additional tests for FES 1.0 Arithmetic operators."""
from django.db.models import Value, Q

from gisserver.parsers.fes20 import Filter
from gisserver.parsers.fes20.expressions import (
    BinaryOperator,
    BinaryOperatorType,
    Literal,
    ValueReference,
)
from gisserver.parsers.fes20.operators import (
    # Importing all these elements directly,
    # so copy-paste from assertion errors works.
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
                <fes:ValueReference>SomeProperty</fes:ValueReference>
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
                                Literal(value=100, type=None),
                                Literal(value=50, type=None),
                            ),
                        ),
                        Literal(value=200, type=None),
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
    assert query == CompiledQuery(
        lookups=[Q(SomeProperty__exact=Value(100) - Value(50) + Value(200))]
    ), repr(query)
