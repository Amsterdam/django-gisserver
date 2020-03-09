"""Integration tests for FES parsing.

This checks whether the examples from the FES specification are properly parsed.
Both the example XML and description (in the docstring) are verbatim from
the "Open GIS Filter Encoding 2.0 Standard" docs.

HTML Version: https://docs.opengeospatial.org/is/09-026r2/09-026r2.html

This test style is inspired by pyfes (which is also Apache licensed)
"""
from decimal import Decimal as D

import pytest
from django.contrib.gis import measure
from django.contrib.gis.geos import GEOSGeometry
from django.db.models import F, Q
from django.db.models.functions import Sin

from gisserver.parsers.fes20 import Filter, parse_fes
from gisserver.parsers.fes20.expressions import Function, Literal, ValueReference
from gisserver.parsers.fes20.functions import function_registry
from gisserver.parsers.fes20.identifiers import ResourceId
from gisserver.parsers.fes20.operators import (
    # Importing all these elements directly,
    # so copy-paste from assertion errors works.
    BetweenComparisonOperator,
    BinaryComparisonName,
    BinaryComparisonOperator,
    BinaryLogicOperator,
    BinaryLogicType,
    BinarySpatialOperator,
    DistanceOperator,
    DistanceOperatorName,
    LikeOperator,
    MatchAction,
    Measure,
    SpatialOperatorName,
    UnaryLogicOperator,
    UnaryLogicType,
)
from gisserver.parsers.fes20.query import FesQuery
from gisserver.parsers.gml import geometries
from gisserver.parsers.gml.geometries import GEOSGMLGeometry
from gisserver.types import WGS84


def test_fes20_c5_example1():
    """A simple non-spatial filter checking to see if SomeProperty is equal to 100."""
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>SomeProperty</fes:ValueReference>
                <fes:Literal>100</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>
    """.strip()
    expected = Filter(
        BinaryComparisonOperator(
            BinaryComparisonName.PropertyIsEqualTo,
            expression=(ValueReference("SomeProperty"), Literal("100"),),
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(lookups=[Q(SomeProperty__exact=100)]), repr(query)


def test_fes20_c5_example2():
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
                <fes:ValueReference>DEPTH</fes:ValueReference>
                <fes:Literal>30</fes:Literal>
            </fes:PropertyIsLessThan>
        </fes:Filter>
    """.strip()
    expected = Filter(
        BinaryComparisonOperator(
            BinaryComparisonName.PropertyIsLessThan,
            expression=(ValueReference("DEPTH"), Literal("30")),
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(lookups=[Q(DEPTH__lt="30")]), repr(query)


def test_fes20_c5_example3():
    """This example encodes a simple spatial filter. In this case, one is
    finding all features that have a geometry that spatially interacts with the
    specified bounding box. The expression NOT DISJOINT is used to exclude all
    features that do not interact with the bounding box; in other words
    identify all the features that interact with the bounding box in some way.
    """
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:gml="http://www.opengis.net/gml/3.2"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd
            http://www.opengis.net/gml/3.2
            http://schemas.opengis.net/gml/3.2.1/gml.xsd">
            <fes:Not>
                <fes:Disjoint>
                    <fes:ValueReference>Geometry</fes:ValueReference>
                    <gml:Envelope srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                        <gml:lowerCorner>13.0983 31.5899</gml:lowerCorner>
                        <gml:upperCorner>35.5472 42.8143</gml:upperCorner>
                    </gml:Envelope>
                </fes:Disjoint>
            </fes:Not>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=UnaryLogicOperator(
            operands=BinarySpatialOperator(
                operatorType=SpatialOperatorName.Disjoint,
                operand1=ValueReference(xpath="Geometry"),
                operand2=GEOSGMLGeometry(
                    srs=WGS84,
                    geos_data=GEOSGeometry(
                        "POLYGON ((13.0983 31.5899, 35.5472 31.5899"
                        ", 35.5472 42.8143, 13.0983 42.8143, 13.0983 31.5899))"
                    ),
                ),
            ),
            operatorType=UnaryLogicType.Not,
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            ~Q(
                Geometry__disjoint=GEOSGeometry(
                    "POLYGON ((13.0983 31.5899, 35.5472 31.5899"
                    ", 35.5472 42.8143, 13.0983 42.8143, 13.0983 31.5899))"
                )
            )
        ]
    ), repr(query)


def test_fes20_c5_example3_b():
    """An alternative encoding of this filter could have used to fes:BBOX element"""
    xml_text = """
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:gml="http://www.opengis.net/gml/3.2"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd
            http://www.opengis.net/gml/3.2
            http://schemas.opengis.net/gml/3.2.1/gml.xsd">
            <fes:BBOX>
                <fes:ValueReference>Geometry</fes:ValueReference>
                <gml:Envelope srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                    <gml:lowerCorner>13.0983 31.5899</gml:lowerCorner>
                    <gml:upperCorner>35.5472 42.8143</gml:upperCorner>
                </gml:Envelope>
            </fes:BBOX>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinarySpatialOperator(
            operatorType=SpatialOperatorName.BBOX,
            operand1=ValueReference(xpath="Geometry"),
            operand2=GEOSGMLGeometry(
                srs=WGS84,
                geos_data=GEOSGeometry(
                    "POLYGON ((13.0983 31.5899, 35.5472 31.5899"
                    ", 35.5472 42.8143, 13.0983 42.8143, 13.0983 31.5899))"
                ),
            ),
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(
                Geometry__bboverlaps=GEOSGeometry(
                    "POLYGON ((13.0983 31.5899, 35.5472 31.5899"
                    ", 35.5472 42.8143, 13.0983 42.8143, 13.0983 31.5899))"
                )
            )
        ]
    ), repr(query)


def test_fes20_c5_example4():
    """In this example, Examples 2 and 3 are combined with the logical
    operator AND. The predicate is thus interpreted as seeking all features
    that interact with the specified bounding box and have a DEPTH value of
    less than 30 m."""
    xml_text = """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:gml="http://www.opengis.net/gml/3.2"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd
             http://www.opengis.net/gml
             http://schemas.opengis.net/gml/2.1.2/geometry.xsd">
            <fes:And>
                <fes:PropertyIsLessThan>
                    <fes:ValueReference>DEPTH</fes:ValueReference>
                    <fes:Literal>30</fes:Literal>
                </fes:PropertyIsLessThan>
                <fes:Not>
                    <fes:Disjoint>
                        <fes:ValueReference>Geometry</fes:ValueReference>
                        <gml:Envelope srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                            <gml:lowerCorner>13.0983 31.5899</gml:lowerCorner>
                            <gml:upperCorner>35.5472 42.8143</gml:upperCorner>
                        </gml:Envelope>
                    </fes:Disjoint>
                </fes:Not>
            </fes:And>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinaryLogicOperator(
            operands=[
                BinaryComparisonOperator(
                    operatorType=BinaryComparisonName.PropertyIsLessThan,
                    expression=(
                        ValueReference(xpath="DEPTH"),
                        Literal(value="30", type=None),
                    ),
                    matchCase=True,
                    matchAction=MatchAction.Any,
                ),
                UnaryLogicOperator(
                    operands=BinarySpatialOperator(
                        operatorType=SpatialOperatorName.Disjoint,
                        operand1=ValueReference(xpath="Geometry"),
                        operand2=GEOSGMLGeometry(
                            srs=WGS84,
                            geos_data=GEOSGeometry(
                                "POLYGON ((13.0983 31.5899, 35.5472 31.5899"
                                ", 35.5472 42.8143, 13.0983 42.8143, 13.0983 31.5899))"
                            ),
                        ),
                    ),
                    operatorType=UnaryLogicType.Not,
                ),
            ],
            operatorType=BinaryLogicType.And,
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(DEPTH__lt="30")
            & ~Q(
                Geometry__disjoint=GEOSGeometry(
                    "POLYGON ((13.0983 31.5899, 35.5472 31.5899"
                    ", 35.5472 42.8143, 13.0983 42.8143, 13.0983 31.5899))"
                )
            )
        ]
    ), repr(query)


def test_fes20_c5_example5():
    """A fes:Filter element can also be used to identify an enumerated set of
    feature instances or feature components. In this case, any operation that
    included this filter block would be limited to the feature instances or
    feature components listed within the fes:Filter element.

    A filter applied to a GML version 3 data store:
    """
    xml_text = """
        <?xml version="1.0"?>
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:ResourceId rid="TREESA_1M.1234"/>
            <fes:ResourceId rid="TREESA_1M.5678"/>
            <fes:ResourceId rid="TREESA_1M.9012"/>
            <fes:ResourceId rid="INWATERA_1M.3456"/>
            <fes:ResourceId rid="INWATERA_1M.7890"/>
            <fes:ResourceId rid="BUILTUPA_1M.4321"/>
        </fes:Filter>
    """.strip()
    expected = Filter(
        [
            ResourceId(rid="TREESA_1M.1234"),
            ResourceId(rid="TREESA_1M.5678"),
            ResourceId(rid="TREESA_1M.9012"),
            ResourceId(rid="INWATERA_1M.3456"),
            ResourceId(rid="INWATERA_1M.7890"),
            ResourceId(rid="BUILTUPA_1M.4321"),
        ]
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(pk="TREESA_1M.1234")
            | Q(pk="TREESA_1M.5678")
            | Q(pk="TREESA_1M.9012")
            | Q(pk="INWATERA_1M.3456")
            | Q(pk="INWATERA_1M.7890")
            | Q(pk="BUILTUPA_1M.4321")
        ]
    ), repr(query)


def test_fes20_c5_example6():
    """The following filter includes the encoding of a function. This filter
    identifies all features where the sine() of the property named
    DISPERSION_ANGLE is 1.
    """

    @function_registry.register(
        name="SIN", arguments=dict(value1="xsd:double"), returns="xsd:double",
    )
    def fes_sin(value1):
        return Sin(value1)

    xml_text = """
        <fes:Filter
        xmlns:fes="http://www.opengis.net/fes/2.0"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.opengis.net/fes/2.0
        http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:Function name="SIN">
                    <fes:ValueReference>DISPERSION_ANGLE</fes:ValueReference>
                </fes:Function>
                <fes:Literal>1</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinaryComparisonOperator(
            operatorType=BinaryComparisonName.PropertyIsEqualTo,
            expression=(
                Function(
                    name="SIN", arguments=[ValueReference(xpath="DISPERSION_ANGLE")],
                ),
                Literal(value="1"),
            ),
            matchCase=True,
            matchAction=MatchAction.Any,
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        annotations={"a1": Sin(F("DISPERSION_ANGLE"))}, lookups=[Q(a1__exact="1")]
    ), repr(query)


def test_fes20_c5_example7():
    """This example assumes that the server advertises support for a function
    called "Add" in its filter capabilities document. The example encodes a
    filter that includes an arithmetic expression. This filter is equivalent
    to the expression PROPA = PROPB + 100.
    """

    @function_registry.register(
        name="Add", arguments=dict(value1="xsd:double"), returns="xsd:double",
    )
    def fes_add(value1: F, value2: str):
        # value1 is already an F value (thanks to ValueReference)
        return value1 + value2

    xml_text = """
        <fes:Filter
        xmlns:fes="http://www.opengis.net/fes/2.0"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.opengis.net/fes/2.0
        http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>PROPA</fes:ValueReference>
                <fes:Function name="Add">
                    <fes:ValueReference>PROPB</fes:ValueReference>
                    <fes:Literal>100</fes:Literal>
                </fes:Function>
            </fes:PropertyIsEqualTo>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinaryComparisonOperator(
            operatorType=BinaryComparisonName.PropertyIsEqualTo,
            expression=(
                ValueReference(xpath="PROPA"),
                Function(
                    name="Add",
                    arguments=[ValueReference(xpath="PROPB"), Literal(value="100")],
                ),
            ),
            matchCase=True,
            matchAction=MatchAction.Any,
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    # Testing against repr() because CombinedExpression / Value doesn't do __eq__ testing.
    query = result.get_query()
    assert repr(query) == repr(
        FesQuery(lookups=[Q(PROPA__exact=F("PROPB") + 100)])
    ), repr(query)


def test_fes20_c5_example8():
    """This example encodes a filter using the BETWEEN operator. The filter
    identifies all features where the DEPTH is between 100 m and 200 m."""
    xml_text = """
        <fes:Filter
        xmlns:fes="http://www.opengis.net/fes/2.0"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.opengis.net/fes/2.0
        http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsBetween>
                <fes:ValueReference>DEPTH</fes:ValueReference>
                <fes:LowerBoundary>
                    <fes:Literal>100</fes:Literal>
                </fes:LowerBoundary>
                <fes:UpperBoundary>
                    <fes:Literal>200</fes:Literal>
                </fes:UpperBoundary>
            </fes:PropertyIsBetween>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BetweenComparisonOperator(
            expression=ValueReference(xpath="DEPTH"),
            lowerBoundary=Literal(value="100"),
            upperBoundary=Literal(value="200"),
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(lookups=[Q(DEPTH__range=("100", "200"))]), repr(query)


def test_fes20_c5_example9():
    """This example is similar to Example 8, except that in this case, the
    filter is checking to see if the SAMPLE_DATE property is within a
    specified date range."""
    xml_text = """
        <fes:Filter
        xmlns:fes="http://www.opengis.net/fes/2.0"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.opengis.net/fes/2.0
        http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsBetween>
                <fes:ValueReference>SAMPLE_DATE</fes:ValueReference>
                <fes:LowerBoundary>
                    <fes:Literal>2001-01-15T20:07:48.11</fes:Literal>
                </fes:LowerBoundary>
                <fes:UpperBoundary>
                    <fes:Literal>2001-03-06T12:00:00.00</fes:Literal>
                </fes:UpperBoundary>
            </fes:PropertyIsBetween>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BetweenComparisonOperator(
            expression=ValueReference(xpath="SAMPLE_DATE"),
            lowerBoundary=Literal(value="2001-01-15T20:07:48.11", type=None),
            upperBoundary=Literal(value="2001-03-06T12:00:00.00", type=None),
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(SAMPLE_DATE__range=("2001-01-15T20:07:48.11", "2001-03-06T12:00:00.00"))
        ]
    ), repr(query)


def test_fes20_c5_example10():
    """This example encodes a filter using the LIKE operation to perform a
    pattern matching comparison. In this case, the filter identifies all
    features where the value of the property named LAST_NAME begins with the
    letters "JOHN"."""
    xml_text = """
        <fes:Filter
        xmlns:fes="http://www.opengis.net/fes/2.0"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.opengis.net/fes/2.0
        http://schemas.opengis.net/filter/2.0/filterAll.xsd">
        <fes:PropertyIsLike wildCard="*" singleChar="#" escapeChar="!">
            <fes:ValueReference>LAST_NAME</fes:ValueReference>
            <fes:Literal>JOHN*</fes:Literal>
        </fes:PropertyIsLike>
    </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=LikeOperator(
            expression=(
                ValueReference(xpath="LAST_NAME"),
                Literal(value="JOHN*", type=None),
            ),
            wildCard="*",
            singleChar="#",
            escapeChar="!",
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(lookups=[Q(LAST_NAME__fes_like="JOHN%")]), repr(query)


def test_fes20_c5_example11():
    """This example encodes a spatial filter that identifies all features whose
    geometry property, named Geometry in this example, overlap a polygonal area
    of interest."""
    xml_text = """
        <fes:Filter
        xmlns:fes="http://www.opengis.net/fes/2.0"
        xmlns:gml="http://www.opengis.net/gml/3.2"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.opengis.net/fes/2.0
        http://schemas.opengis.net/filter/2.0/filterAll.xsd
        http://www.opengis.net/gml/3.2
        http://schemas.opengis.net/gml/3.2.1/gml.xsd">
        <fes:Overlaps>
            <fes:ValueReference>Geometry</fes:ValueReference>
            <gml:Polygon gml:id="P1" srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                <gml:exterior>
                    <gml:LinearRing>
                        <gml:posList>10 10 20 20 30 30 40 40 10 10</gml:posList>
                    </gml:LinearRing>
                </gml:exterior>
            </gml:Polygon>
        </fes:Overlaps>
    </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinarySpatialOperator(
            operatorType=SpatialOperatorName.Overlaps,
            operand1=ValueReference(xpath="Geometry"),
            operand2=geometries.GEOSGMLGeometry(
                srs=WGS84,
                geos_data=GEOSGeometry("POLYGON ((10 10, 20 20, 30 30, 40 40, 10 10))"),
            ),
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(
                Geometry__overlaps=GEOSGeometry(
                    "POLYGON ((10 10, 20 20, 30 30, 40 40, 10 10))"
                )
            )
        ]
    ), repr(query)


def test_fes20_c5_example11_b():
    """Although GML 3.2 is the canonical GML version supported by this
    International Standard, the filter schemas have been crafted is such a way
    as to support any version of GML.  For example, here is the same filter
    expression expect that it GML 2.1.2 to encoding the geometry rather than
    GML 3.2:"""
    xml_text = """
        <?xml version="1.0"?>
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:gml="http://www.opengis.net/gml"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://www.pvretano.com/schemas/filter/2.0/filterAll.xsd
           http://www.opengis.net/gml
           http://www.pvretano.com/schemas/gml/2.1.2/geometry.xsd">
           <fes:Overlaps>
              <fes:ValueReference>Geometry</fes:ValueReference>
              <gml:Polygon srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                 <gml:outerBoundaryIs>
                    <gml:LinearRing>
                       <gml:coordinates>10,10 20,20 30,30 40,40 10,10</gml:coordinates>
                    </gml:LinearRing>
                 </gml:outerBoundaryIs>
              </gml:Polygon>
           </fes:Overlaps>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinarySpatialOperator(
            operatorType=SpatialOperatorName.Overlaps,
            operand1=ValueReference(xpath="Geometry"),
            operand2=geometries.GEOSGMLGeometry(
                srs=WGS84,
                geos_data=GEOSGeometry("POLYGON ((10 10, 20 20, 30 30, 40 40, 10 10))"),
            ),
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(
                Geometry__overlaps=GEOSGeometry(
                    "POLYGON ((10 10, 20 20, 30 30, 40 40, 10 10))"
                )
            )
        ]
    ), repr(query)


def test_fes20_c5_example12():
    """In this example, a more complex scalar predicate is encoded using the
    logical operators AND and OR. The example is equivalent to the expression:

    ((FIELD1=10 OR FIELD1=20) AND (STATUS="VALID"))
    """
    xml_text = """
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://schemas.opengis.net/filter/2.0/filterAll.xsd">
           <fes:And>
              <fes:Or>
                 <fes:PropertyIsEqualTo>
                    <fes:ValueReference>FIELD1</fes:ValueReference>
                    <fes:Literal>10</fes:Literal>
                 </fes:PropertyIsEqualTo>
                 <fes:PropertyIsEqualTo>
                    <fes:ValueReference>FIELD1</fes:ValueReference>
                    <fes:Literal>20</fes:Literal>
                 </fes:PropertyIsEqualTo>
              </fes:Or>
              <fes:PropertyIsEqualTo>
                 <fes:ValueReference>STATUS</fes:ValueReference>
                 <fes:Literal>VALID</fes:Literal>
              </fes:PropertyIsEqualTo>
           </fes:And>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinaryLogicOperator(
            operands=[
                BinaryLogicOperator(
                    operands=[
                        BinaryComparisonOperator(
                            operatorType=BinaryComparisonName.PropertyIsEqualTo,
                            expression=(
                                ValueReference(xpath="FIELD1"),
                                Literal(value="10"),
                            ),
                            matchCase=True,
                            matchAction=MatchAction.Any,
                        ),
                        BinaryComparisonOperator(
                            operatorType=BinaryComparisonName.PropertyIsEqualTo,
                            expression=(
                                ValueReference(xpath="FIELD1"),
                                Literal(value="20"),
                            ),
                            matchCase=True,
                            matchAction=MatchAction.Any,
                        ),
                    ],
                    operatorType=BinaryLogicType.Or,
                ),
                BinaryComparisonOperator(
                    operatorType=BinaryComparisonName.PropertyIsEqualTo,
                    expression=(
                        ValueReference(xpath="STATUS"),
                        Literal(value="VALID"),
                    ),
                    matchCase=True,
                    matchAction=MatchAction.Any,
                ),
            ],
            operatorType=BinaryLogicType.And,
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            (Q(FIELD1__exact="10") | Q(FIELD1__exact="20")) & Q(STATUS__exact="VALID")
        ]
    ), repr(query)


def test_fes20_c5_example13():
    """Spatial and non-spatial predicates can be encoded in a single filter
    expression. In this example, a spatial predicate checks to see if the
    geometric property WKB_GEOMlies within a region of interest defined by a
    polygon and a scalar predicate check to see if the scalar property DEPTH
    lies within a specified range. This example encoding is equivalent to the
    expression:

    (wkb_geom WITHIN "some polygon") AND (depth BETWEEN 400 AND 800)
    """
    xml_text = """
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:gml="http://www.opengis.net/gml/3.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://schemas.opengis.net/filter/2.0/filterAll.xsd
           http://www.opengis.net/gml/3.2
           http://schemas.opengis.net/gml/3.2.1/gml.xsd">
           <fes:And>
              <fes:Within>
                 <fes:ValueReference>WKB_GEOM</fes:ValueReference>
                 <gml:Polygon gml:id="P1" srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                    <gml:exterior>
                       <gml:LinearRing>
                          <gml:posList>10 10 20 20 30 30 40 40 10 10</gml:posList>
                       </gml:LinearRing>
                    </gml:exterior>
                 </gml:Polygon>
              </fes:Within>
              <fes:PropertyIsBetween>
                 <fes:ValueReference>DEPTH</fes:ValueReference>
                 <fes:LowerBoundary>
                    <fes:Literal>400</fes:Literal>
                 </fes:LowerBoundary>
                 <fes:UpperBoundary>
                    <fes:Literal>800</fes:Literal>
                 </fes:UpperBoundary>
              </fes:PropertyIsBetween>
           </fes:And>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=BinaryLogicOperator(
            operands=[
                BinarySpatialOperator(
                    operatorType=SpatialOperatorName.Within,
                    operand1=ValueReference(xpath="WKB_GEOM"),
                    operand2=geometries.GEOSGMLGeometry(
                        srs=WGS84,
                        geos_data=GEOSGeometry(
                            "POLYGON ((10 10, 20 20, 30 30, 40 40, 10 10))"
                        ),
                    ),
                ),
                BetweenComparisonOperator(
                    expression=ValueReference(xpath="DEPTH"),
                    lowerBoundary=Literal(value="400", type=None),
                    upperBoundary=Literal(value="800", type=None),
                ),
            ],
            operatorType=BinaryLogicType.And,
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(
                WKB_GEOM__within=GEOSGeometry(
                    "POLYGON ((10 10, 20 20, 30 30, 40 40, 10 10))"
                )
            )
            & Q(DEPTH__range=("400", "800"))
        ]
    ), repr(query)


def test_fes20_c5_example14():
    """This example restricts the active set of objects to those instances of
    the Person type that are older than 50 years old and live in Toronto. This
    filter expression uses an XPath (as given in W3C XML Path Language)
    expression to reference the complex attributes of the Person type.
    """
    xml_text = """
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://schemas.opengis.net/filter/2.0/filterAll.xsd">
           <fes:And>
              <fes:PropertyIsGreaterThan>
                 <fes:ValueReference>Person/age</fes:ValueReference>
                 <fes:Literal>50</fes:Literal>
              </fes:PropertyIsGreaterThan>
              <fes:PropertyIsEqualTo>
                 <fes:ValueReference>Person/mailAddress/Address/city</fes:ValueReference>
                 <fes:Literal>Toronto</fes:Literal>
              </fes:PropertyIsEqualTo>
           </fes:And>
        </fes:Filter>
    """.strip()
    result = parse_fes(xml_text)
    expected = Filter(
        predicate=BinaryLogicOperator(
            operands=[
                BinaryComparisonOperator(
                    operatorType=BinaryComparisonName.PropertyIsGreaterThan,
                    expression=(
                        ValueReference(xpath="Person/age"),
                        Literal(value="50"),
                    ),
                    matchCase=True,
                    matchAction=MatchAction.Any,
                ),
                BinaryComparisonOperator(
                    operatorType=BinaryComparisonName.PropertyIsEqualTo,
                    expression=(
                        ValueReference(xpath="Person/mailAddress/Address/city"),
                        Literal(value="Toronto"),
                    ),
                    matchCase=True,
                    matchAction=MatchAction.Any,
                ),
            ],
            operatorType=BinaryLogicType.And,
        )
    )
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(Person__age__gt="50")
            & Q(Person__mailAddress__Address__city__exact="Toronto")
        ]
    ), repr(query)


def test_fes20_c5_example15():
    """This example finds features within a specified distance of a geometry."""
    xml_text = """
        <?xml version="1.0"?>
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:gml="http://www.opengis.net/gml/3.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://schemas.opengis.net/filter/2.0/filterAll.xsd
           http://www.opengis.net/gml/3.2
           http://schemas.opengis.net/gml/3.2.1/gml.xsd">
           <fes:DWithin>
              <fes:ValueReference>geometry</fes:ValueReference>
              <gml:Point gml:id="P1" srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                 <gml:pos>43.716589 -79.340686</gml:pos>
              </gml:Point>
              <fes:Distance uom="m">10</fes:Distance>
           </fes:DWithin>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=DistanceOperator(
            valueReference=ValueReference(xpath="geometry"),
            operatorType=DistanceOperatorName.DWithin,
            geometry=geometries.GEOSGMLGeometry(
                srs=WGS84,
                geos_data=GEOSGeometry("POINT (43.716589 -79.34068600000001)"),
            ),
            distance=Measure(value=D("10"), uom="m"),
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(
                geometry__distance_lte=(
                    GEOSGeometry("POINT (43.716589 -79.34068600000001)"),
                    measure.Distance(m=10.0),
                )
            )
        ]
    ), repr(query)


def test_fes20_c7_example1():
    """C.7 Temporal filter example

    EXAMPLE 1
    The following examples for temporal comparisons are provided to illustrate
    the proper use of the temporal  The examples are based on the
    following sample GML:"""
    xml_text = """
        <?xml version="1.0"?>
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:gml="http://www.opengis.net/gml/3.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://schemas.opengis.net/filter/2.0/filterAll.xsd
           http://www.opengis.net/gml/3.2
           http://schemas.opengis.net/gml/3.2.1/gml.xsd">
           <fes:DWithin>
              <fes:ValueReference>geometry</fes:ValueReference>
              <gml:Point gml:id="P1" srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                 <gml:pos>43.716589 -79.340686</gml:pos>
              </gml:Point>
              <fes:Distance uom="m">10</fes:Distance>
           </fes:DWithin>
        </fes:Filter>
    """.strip()
    expected = Filter(
        predicate=DistanceOperator(
            valueReference=ValueReference(xpath="geometry"),
            operatorType=DistanceOperatorName.DWithin,
            geometry=geometries.GEOSGMLGeometry(
                srs=WGS84,
                geos_data=GEOSGeometry("POINT (43.716589 -79.34068600000001)"),
            ),
            distance=Measure(value=10, uom="m"),
        )
    )
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    # Test SQL generating
    query = result.get_query()
    assert query == FesQuery(
        lookups=[
            Q(
                geometry__distance_lte=(
                    GEOSGeometry("POINT (43.716589 -79.34068600000001)"),
                    measure.Distance(m=10),
                )
            )
        ]
    ), repr(query)


@pytest.mark.skip
def test_fes20_c7_example2():
    """Time instant to time instant:"""
    xml_text = """
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:gml="http://www.opengis.net/gml/3.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://schemas.opengis.net/filter/2.0/filterAll.xsd
           http://www.opengis.net/gml/3.2
           http://schemas.opengis.net/gml/3.2.1/gml.xsd">
           <fes:TEquals>
              <fes:ValueReference>SimpleTrajectory/pathGeometry/gml:MovingObjectStatus[1]/  gml:validTime/gml:TimeInstant</fes:ValueReference>
              <gml:TimeInstant gml:id="TI1">
                 <gml:timePosition>2005-05-19T09:28:40Z</gml:timePosition>
              </gml:TimeInstant>
           </fes:TEquals>
        </fes:Filter>
    """.strip()  # noqa: E501
    expected = Filter([])
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    print(result.get_query())


@pytest.mark.skip(reason="GML Temporal support is incomplete")
def test_fes20_c7_example3():
    """Time instant to time instant:"""
    xml_text = """
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:gml="http://www.opengis.net/gml/3.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://schemas.opengis.net/filter/2.0/filterAll.xsd
           http://www.opengis.net/gml/3.2
           http://schemas.opengis.net/gml/3.2.1/gml.xsd">
           <fes:TContains>
              <fes:ValueReference>SimpleTrajectory/gml:TimePeriod</fes:ValueReference>
              <gml:TimeInstant gml:id="TI1">
                 <gml:timePosition>2005-05-20T02:45:00-05:00</gml:timePosition>
              </gml:TimeInstant>
           </fes:TContains>
        </fes:Filter>
    """.strip()
    expected = Filter([])
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    print(result.get_query())


@pytest.mark.skip(reason="GML Temporal support is incomplete")
def test_fes20_c7_example4():
    """Time instant to time instant:"""
    xml_text = """
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:gml="http://www.opengis.net/gml/3.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://schemas.opengis.net/filter/2.0/filterAll.xsd
           http://www.opengis.net/gml/3.2
           http://schemas.opengis.net/gml/3.2.1/gml.xsd">
           <fes:During>
              <fes:ValueReference>SimpleTrajectory/pathGeometry/gml:MovingObjectStatus[1]/gml:validTime/gml:TimeInstant</fes:ValueReference>
              <gml:TimePeriod gml:id="TP1">
                 <gml:begin>
                    <gml:TimeInstant gml:id="TI1">
                       <gml:timePosition>2005-05-17T00:00:00Z</gml:timePosition>
                    </gml:TimeInstant>
                 </gml:begin>
                 <gml:end>
                    <gml:TimeInstant gml:id="TI2">
                       <gml:timePosition>2005-05-23T00:00:00Z</gml:timePosition>
                    </gml:TimeInstant>
                 </gml:end>
              </gml:TimePeriod>
           </fes:During>
        </fes:Filter>
    """.strip()
    expected = Filter([])
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    print(result.get_query())


@pytest.mark.skip(reason="GML Temporal support is incomplete")
def test_fes20_c7_example5():
    """Time period to time period:"""
    xml_text = """
        <fes:Filter
           xmlns:fes="http://www.opengis.net/fes/2.0"
           xmlns:gml="http://www.opengis.net/gml/3.2"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:schemaLocation="http://www.opengis.net/fes/2.0
           http://schemas.opengis.net/filter/2.0/filterAll.xsd
           http://www.opengis.net/gml/3.2
           http://schemas.opengis.net/gml/3.2.1/gml.xsd">
          <fes:TOverlaps>
            <fes:ValueReference>SimpleTrajectory/gml:TimePeriod</fes:ValueReference>
            <gml:TimePeriod gml:id="TP1">
              <gml:begin>
                <gml:TimeInstant gml:id="TI1">
                  <gml:timePosition>2005-05-17T08:00:00Z</gml:timePosition>
                </gml:TimeInstant>
              </gml:begin>
              <gml:end>
                <gml:TimeInstant gml:id="TI2">
                  <gml:timePosition>2005-05-23T11:00:00Z</gml:timePosition>
                </gml:TimeInstant>
              </gml:end>
            </gml:TimePeriod>
          </fes:TOverlaps>
        </fes:Filter>
    """.strip()
    expected = Filter([])
    result = parse_fes(xml_text)
    assert result == expected, f"result={result!r}"

    print(result.get_query())
