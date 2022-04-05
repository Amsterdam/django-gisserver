import sys

from gisserver import conf
from gisserver.exceptions import (
    OperationParsingFailed,
    OperationProcessingFailed,
)


# Despite efforts to sync the PROJ.4 definitions, there is still a minor difference
# between platforms, or library versions that cause coordinate shifts. Hopefully,
# no other changes are visible. Hence keeping these here for now. If there are more
# differences on other platforms, better perform a live transformation here to see
# what the expected values will be.
#
# Note that GeoJSON coordinates are always ESPG:4326 in (longitude, latitude)
if sys.platform == "darwin":
    if conf.GISSERVER_USE_DB_RENDERING:
        # PostgreSQL determines the results.
        POINT1_EWKT = "POINT(4.90876101285122 52.3631712637357)"
        POINT1_GEOJSON = [4.90876101285122, 52.3631712637357]
        POINT1_XML_WGS84 = "4.90876101285122 52.363171263736"
        POINT1_XML_RD = "122411.00009179 486250.000461"

        POINT2_EWKT = "POINT(4.90890394393253 52.363531349932)"
        POINT2_GEOJSON = [4.90890394393253, 52.363531349932]
        POINT2_XML_WGS84 = "4.90890394393253 52.363531349932"
    else:
        POINT1_EWKT = "POINT (4.908761012851219 52.36317126373572)"
        POINT1_GEOJSON = [4.908761012851219, 52.363171263735715]
        POINT1_XML_WGS84 = "4.908761012851219 52.363171263735715"
        POINT1_XML_RD = "122411.00000717948 486250.0005178676"

        POINT2_EWKT = "POINT (4.908903943932534 52.36353134993197)"
        POINT2_GEOJSON = [4.908903943932534, 52.36353134993197]
        POINT2_XML_WGS84 = "4.908903943932534 52.36353134993197"
else:
    if conf.GISSERVER_USE_DB_RENDERING:
        POINT1_EWKT = "POINT(4.90876101285122 52.3631712637357)"
        POINT1_GEOJSON = [4.90876101285122, 52.3631712637357]
        POINT1_XML_WGS84 = "4.90876101285122 52.363171263736"
        POINT1_XML_RD = "122411.00009179 486250.00046099"

        POINT2_EWKT = "POINT(4.90890394393253 52.3635313499319)"
        POINT2_GEOJSON = [4.90890394393253, 52.3635313499319]
        POINT2_XML_WGS84 = "4.90890394393253 52.363531349932"
    else:
        POINT1_EWKT = "POINT (4.90876101285122 52.36317126373569)"
        POINT1_GEOJSON = [4.90876101285122, 52.36317126373569]
        POINT1_XML_WGS84 = "4.90876101285122 52.36317126373569"
        POINT1_XML_RD = "122411.00000717954 486250.0005178673"

        POINT2_EWKT = "POINT (4.908903943932534 52.36353134993195)"
        POINT2_GEOJSON = [4.908903943932534, 52.36353134993195]
        POINT2_XML_WGS84 = "4.908903943932534 52.36353134993195"


FILTERS = {
    "simple": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsGreaterThanOrEqualTo>
                <fes:ValueReference>rating</fes:ValueReference>
                <fes:Literal>3.0</fes:Literal>
            </fes:PropertyIsGreaterThanOrEqualTo>
        </fes:Filter>""",
    "value_datetimefield": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:Literal>2020-04-05T12:11:10+00:00</fes:Literal>
                <fes:ValueReference>created</fes:ValueReference>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    "value_boolean": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>is_open</fes:ValueReference>
                <fes:Literal>true</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    "value_boolean_cast": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xs="http://www.w3.org/2001/XMLSchema">
            <fes:PropertyIsEqualTo>
                <fes:Literal type="xs:boolean">true</fes:Literal>
                <fes:ValueReference>is_open</fes:ValueReference>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    "value_array": """
        <?xml version="1.0"?>
        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>tags</fes:ValueReference>
                <fes:Literal>black</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    "value_array_lt": """
        <?xml version="1.0"?>
        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:PropertyIsLessThan>
                <fes:ValueReference>tags</fes:ValueReference>
                <fes:Literal>color</fes:Literal>
            </fes:PropertyIsLessThan>
        </fes:Filter>""",
    "fes1": """
        <Filter>
            <PropertyIsGreaterThanOrEqualTo>
                <PropertyName>rating</PropertyName>
                <Literal>3.0</Literal>
            </PropertyIsGreaterThanOrEqualTo>
        </Filter>""",
    "like": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!">
                <fes:ValueReference>name</fes:ValueReference>
                <fes:Literal>C?fé*</fes:Literal>
            </fes:PropertyIsLike>
        </fes:Filter>""",
    "bbox": """
        <?xml version="1.0"?>
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:gml="http://www.opengis.net/gml/3.2"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd
            http://www.opengis.net/gml/3.2
            http://schemas.opengis.net/gml/3.2.1/gml.xsd">
            <fes:BBOX>
                <fes:ValueReference>location</fes:ValueReference>
                <gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992">
                    <gml:lowerCorner>122410 486240</gml:lowerCorner>
                    <gml:upperCorner>122412 486260</gml:upperCorner>
                </gml:Envelope>
            </fes:BBOX>
        </fes:Filter>""",
    "bbox_default": """
        <fes:Filter
            xmlns:ns16="http://example.org/gisserver"
            xmlns:wfs="http://www.opengis.net/wfs/2.0"
            xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:BBOX>
                <gml:Envelope xmlns:gml="http://www.opengis.net/gml/3.2"
                              srsName="urn:ogc:def:crs:EPSG::28992">
                    <gml:lowerCorner>122410 486240</gml:lowerCorner>
                    <gml:upperCorner>122412 486260</gml:upperCorner>
                </gml:Envelope>
            </fes:BBOX>
        </fes:Filter>""",
    "and": """
        <?xml version="1.0"?>
        <fes:Filter
            xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:gml="http://www.opengis.net/gml/3.2"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd
            http://www.opengis.net/gml/3.2
            http://schemas.opengis.net/gml/3.2.1/gml.xsd">
            <fes:And>
                <fes:PropertyIsGreaterThanOrEqualTo>
                    <fes:ValueReference>rating</fes:ValueReference>
                    <fes:Literal>3.0</fes:Literal>
                </fes:PropertyIsGreaterThanOrEqualTo>
                <fes:BBOX>
                    <fes:ValueReference>location</fes:ValueReference>
                    <gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992">
                        <gml:lowerCorner>122410 486240</gml:lowerCorner>
                        <gml:upperCorner>122412 486260</gml:upperCorner>
                    </gml:Envelope>
                </fes:BBOX>
            </fes:And>
        </fes:Filter>""",
    "gml:name": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>gml:name</fes:ValueReference>
                <fes:Literal>Café Noir</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
}

COMPLEX_FILTERS = {
    "equal": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>city/name</fes:ValueReference>
                <fes:Literal>CloudCity</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    "equal_xmlns": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>app:city/app:name</fes:ValueReference>
                <fes:Literal>CloudCity</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    "not_nil": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:Not>
                <fes:PropertyIsNil>
                    <fes:ValueReference>city/name</fes:ValueReference>
                </fes:PropertyIsNil>
            </fes:Not>
        </fes:Filter>""",
    "m2m": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>app:opening_hours/app:start_time</fes:ValueReference>
                <fes:Literal>16:00:00</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
}


FLATTENED_FILTERS = {
    "equal": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>city-name</fes:ValueReference>
                <fes:Literal>CloudCity</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    "equal_xmlns": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>app:city-name</fes:ValueReference>
                <fes:Literal>CloudCity</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    "not_nil": """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:Not>
                <fes:PropertyIsNil>
                    <fes:ValueReference>city-name</fes:ValueReference>
                </fes:PropertyIsNil>
            </fes:Not>
        </fes:Filter>""",
}

INVALID_FILTERS = {
    "syntax": (
        """<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">FDFDS</fes:Filter""",
        OperationParsingFailed(
            "filter",
            "Unable to parse FILTER argument: unclosed token: line 1, column 60",
        ),
    ),
    "missing_xmlns": (
        """<?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsGreaterThanOrEqualTo>
                <fes:ValueReference>rating</fes:ValueReference>
                <fes:Literal>3.0</fes:Literal>
            </fes:PropertyIsGreaterThanOrEqualTo>
        </fes:Filter>""",
        OperationParsingFailed(
            "filter",
            "Unable to parse FILTER argument: unbound prefix: line 2, column 8",
        ),
    ),
    "closing_tag": (
        """
    <fes:Filter
         xmlns:fes="http://www.opengis.net/fes/2.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://www.opengis.net/fes/2.0
         http://schemas.opengis.net/filter/2.0/filterAll.xsd">
        <fes:PropertyIsGreaterThanOrEqualTo>
            <fes:ValueReference>rating</fes:ValueReference>
            <fes:Literal>3.0</fes:Literal>
        </fes:PropertyIsGreaterThanOrEqualTofoo>
    </fes:Filter>""",
        OperationParsingFailed(
            "filter",
            "Unable to parse FILTER argument: mismatched tag: line 9, column 10",
        ),
    ),
    "float_text": (
        """
    <fes:Filter
         xmlns:fes="http://www.opengis.net/fes/2.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://www.opengis.net/fes/2.0
         http://schemas.opengis.net/filter/2.0/filterAll.xsd">
        <fes:PropertyIsGreaterThanOrEqualTo>
            <fes:ValueReference>rating</fes:ValueReference>
            <fes:Literal>TEXT</fes:Literal>
        </fes:PropertyIsGreaterThanOrEqualTo>
    </fes:Filter>""",
        OperationParsingFailed(
            "filter",
            "Invalid data for the 'rating' property: Can't cast 'TEXT' to double.",
        ),
    ),
    "float_like": (
        """
    <fes:Filter
         xmlns:fes="http://www.opengis.net/fes/2.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://www.opengis.net/fes/2.0
         http://schemas.opengis.net/filter/2.0/filterAll.xsd">
        <fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="\\">
            <fes:ValueReference>rating</fes:ValueReference>
            <fes:Literal>2</fes:Literal>
        </fes:PropertyIsLike>
    </fes:Filter>""",
        OperationProcessingFailed(
            "filter",
            "Operator '{http://www.opengis.net/fes/2.0}PropertyIsLike'"
            " is not supported for the 'rating' property.",
        ),
    ),
    "date_number": (
        # this also tests auto_cast() logic for Literal,
        # which get_prop_value() doesn't handle well.
        """
    <fes:Filter
         xmlns:fes="http://www.opengis.net/fes/2.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://www.opengis.net/fes/2.0
         http://schemas.opengis.net/filter/2.0/filterAll.xsd">
        <fes:PropertyIsEqualTo>
            <fes:ValueReference>created</fes:ValueReference>
            <fes:Literal>21</fes:Literal>
        </fes:PropertyIsEqualTo>
    </fes:Filter>""",
        OperationParsingFailed(
            "filter",
            "Invalid data for the 'created' property:"
            " Date must be in YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format.",
        ),
    ),
    "date_text": (
        """
    <fes:Filter
         xmlns:fes="http://www.opengis.net/fes/2.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://www.opengis.net/fes/2.0
         http://schemas.opengis.net/filter/2.0/filterAll.xsd">
        <fes:PropertyIsGreaterThanOrEqualTo>
            <fes:ValueReference>created</fes:ValueReference>
            <fes:Literal>abc</fes:Literal>
        </fes:PropertyIsGreaterThanOrEqualTo>
    </fes:Filter>""",
        OperationParsingFailed(
            "filter",
            "Invalid data for the 'created' property:"
            " Date must be in YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format.",
        ),
    ),
    "geometry_lte": (
        # There is so much wrong with this filter that I don't see why
        # this is part of the CITE conformance test suite. It's valid
        # for the XSD schema, but invalid for the application logic.
        """
    <Filter
        xmlns="http://www.opengis.net/fes/2.0"
        xmlns:wfs="http://www.opengis.net/wfs/2.0">
        <PropertyIsLessThanOrEqualTo matchAction="Any" matchCase="true">
            <Literal>
                <gml:Envelope xmlns:gml="http://www.opengis.net/gml/3.2"
                              srsName="urn:ogc:def:crs:EPSG::4326">
                    <gml:lowerCorner>-90 -180</gml:lowerCorner>
                    <gml:upperCorner>90 180</gml:upperCorner>
                </gml:Envelope>
            </Literal>
            <ValueReference
                xmlns:gml="http://www.opengis.net/gml/3.2">gml:boundedBy</ValueReference>
        </PropertyIsLessThanOrEqualTo>
    </Filter>""",
        OperationProcessingFailed(
            "filter",
            "Operator '{http://www.opengis.net/fes/2.0}PropertyIsLessThanOrEqualTo'"
            " does not support comparing geometry properties: 'gml:boundedBy'.",
        ),
    ),
}

SORT_BY = {
    "name": ("name", ["Café Noir", "Foo Bar"]),
    "name-a": ("name A", ["Café Noir", "Foo Bar"]),
    "name-asc": ("name ASC", ["Café Noir", "Foo Bar"]),
    "name-d": ("name D", ["Foo Bar", "Café Noir"]),
    "name-desc": ("name DESC", ["Foo Bar", "Café Noir"]),
    "rating-desc": ("rating DESC", ["Café Noir", "Foo Bar"]),
    "rating,name-asc": ("rating,name ASC", ["Foo Bar", "Café Noir"]),
}
