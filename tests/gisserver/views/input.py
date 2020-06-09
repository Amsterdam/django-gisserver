import django
import sys
from gisserver import conf

# Despite efforts to sync the PROJ.4 definitions, there is still a minor difference
# between platforms, or library versions that cause coordinate shifts. Hopefully,
# no other changes are visible. Hence keeping these here for now. If there are more
# differences on other platforms, better perform a live transformation here to see
# what the expected values will be.
if sys.platform == "darwin":
    if conf.GISSERVER_USE_DB_RENDERING:
        # PostgreSQL determines the results.
        POINT1_XML_WGS84 = "4.90876101285122 52.363171263736"
        POINT1_XML_RD = "122411.00009179 486250.000461"
        # GeoJSON: less decimals then expected
        POINT1_GEOJSON = [4.90876101285122, 52.3631712637357]
        POINT2_GEOJSON = [4.90890394393253, 52.363531349932]
    else:
        POINT1_XML_WGS84 = "4.908761012851219 52.363171263735715"
        POINT1_XML_RD = "122411.00000717948 486250.0005178676"
        # GeoJSON is always WGS84
        POINT1_GEOJSON = [4.908761012851219, 52.363171263735715]
        POINT2_GEOJSON = [4.908903943932534, 52.36353134993197]
else:
    if conf.GISSERVER_USE_DB_RENDERING:
        POINT1_XML_WGS84 = "4.90876101285122 52.363171263736"
        POINT1_XML_RD = "122411.00009179 486250.00046099"
        POINT1_GEOJSON = [4.90876101285122, 52.3631712637357]
        POINT2_GEOJSON = [4.90890394393253, 52.3635313499319]
    else:
        POINT1_XML_WGS84 = "4.90876101285122 52.36317126373569"
        POINT1_XML_RD = "122411.00000717954 486250.0005178673"
        POINT1_GEOJSON = [4.90876101285122, 52.36317126373569]
        POINT2_GEOJSON = [4.908903943932534, 52.36353134993195]


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
}

INVALID_FILTERS = {
    "syntax": (
        """<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">FDFDS</fes:Filter""",
        "Unable to parse FILTER argument: unclosed token: line 1, column 60",
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
        "Unable to parse FILTER argument: unbound prefix: line 2, column 8",
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
        "Unable to parse FILTER argument: mismatched tag: line 9, column 10",
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
        (
            "Invalid filter query: Field 'rating' expected a number but got 'TEXT'."
            if django.VERSION >= (3, 0)
            else "Invalid filter query: could not convert string to float: 'TEXT'"
        ),
    ),
}

SORT_BY = {
    "name": ("name", ["Café Noir", "Foo Bar"]),
    "name-asc": ("name ASC", ["Café Noir", "Foo Bar"]),
    "name-desc": ("name DESC", ["Foo Bar", "Café Noir"]),
    "rating-desc": ("rating DESC", ["Café Noir", "Foo Bar"]),
    "rating,name-asc": ("rating,name ASC", ["Foo Bar", "Café Noir"]),
}
