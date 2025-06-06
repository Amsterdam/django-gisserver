from gisserver.exceptions import OperationParsingFailed, OperationProcessingFailed
from tests.requests import Url

# Tuples of the shape (name, url_type, filter)
FILTERS = [
    (
        "simple",
        Url.NORMAL,
        """
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
    ),
    (
        "value_datetimefield",
        Url.NORMAL,
        """
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
    ),
    (
        "value_boolean",
        Url.NORMAL,
        """
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
    ),
    (
        "value_boolean_cast",
        Url.NORMAL,
        """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xs="http://www.w3.org/2001/XMLSchema">
            <fes:PropertyIsEqualTo>
                <fes:Literal type="xs:boolean">true</fes:Literal>
                <fes:ValueReference>is_open</fes:ValueReference>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    ),
    (
        "value_array",
        Url.NORMAL,
        """
        <?xml version="1.0"?>
        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>tags</fes:ValueReference>
                <fes:Literal>black</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    ),
    (
        "value_array_lt",
        Url.NORMAL,
        """
        <?xml version="1.0"?>
        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:PropertyIsLessThan>
                <fes:ValueReference>tags</fes:ValueReference>
                <fes:Literal>color</fes:Literal>
            </fes:PropertyIsLessThan>
        </fes:Filter>""",
    ),
    (
        "fes1",
        Url.NORMAL,
        """
        <Filter>
            <PropertyIsGreaterThanOrEqualTo>
                <PropertyName>rating</PropertyName>
                <Literal>3.0</Literal>
            </PropertyIsGreaterThanOrEqualTo>
        </Filter>""",
    ),
    (
        "like",
        Url.NORMAL,
        """
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
    ),
    (
        "like_array",
        Url.NORMAL,
        """
        <?xml version="1.0"?>
        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:PropertyIsLike wildCard="*" singleChar="?" escapeChar="!">
                <fes:ValueReference>tags</fes:ValueReference>
                <fes:Literal>blac*</fes:Literal>
            </fes:PropertyIsLike>
        </fes:Filter>""",
    ),
    (
        "bbox",
        Url.NORMAL,
        """
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
    ),
    (
        "bbox_default",
        Url.NORMAL,
        """
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
    ),
    (
        "bbox_wgs84",
        Url.NORMAL,
        """
        <fes:Filter
            xmlns:ns16="http://example.org/gisserver"
            xmlns:wfs="http://www.opengis.net/wfs/2.0"
            xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:BBOX>
                <gml:Envelope xmlns:gml="http://www.opengis.net/gml/3.2"
                              srsName="urn:ogc:def:crs:EPSG::4326">
                    <gml:lowerCorner>52.36308132956971 4.908747234134033</gml:lowerCorner>
                    <gml:upperCorner>52.36326119473073 4.908774657180266</gml:upperCorner>
                </gml:Envelope>
            </fes:BBOX>
        </fes:Filter>""",
    ),
    (
        "bbox_crs84",
        Url.NORMAL,
        """
        <fes:Filter
            xmlns:wfs="http://www.opengis.net/wfs/2.0"
            xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:BBOX>
                <gml:Envelope xmlns:gml="http://www.opengis.net/gml/3.2"
                              srsName="urn:ogc:def:crs:OGC::CRS84">
                    <gml:lowerCorner>4.908747234134033 52.36308132956971</gml:lowerCorner>
                    <gml:upperCorner>4.908774657180266 52.36326119473073</gml:upperCorner>
                </gml:Envelope>
            </fes:BBOX>
        </fes:Filter>""",
    ),
    (
        "bbox_epsg_old",
        Url.NORMAL,
        """
        <fes:Filter
            xmlns:wfs="http://www.opengis.net/wfs/2.0"
            xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:BBOX>
                <gml:Envelope xmlns:gml="http://www.opengis.net/gml/3.2"
                              srsName="EPSG:4326">
                    <gml:lowerCorner>4.908747234134033 52.36308132956971</gml:lowerCorner>
                    <gml:upperCorner>4.908774657180266 52.36326119473073</gml:upperCorner>
                </gml:Envelope>
            </fes:BBOX>
        </fes:Filter>""",
    ),
    (
        "and",
        Url.NORMAL,
        """
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
    ),
    (
        "gml:name",
        Url.NORMAL,
        """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xmlns:gml="http://www.opengis.net/gml/3.2"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>gml:name</fes:ValueReference>
                <fes:Literal>Café Noir</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    ),
    (
        "not_nil_geometry",
        Url.NORMAL,
        """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:Not>
                <fes:PropertyIsNil>
                    <fes:ValueReference>location</fes:ValueReference>
                </fes:PropertyIsNil>
            </fes:Not>
        </fes:Filter>""",
        2,
    ),
    (
        "not_null_geometry",
        Url.NORMAL,
        """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:Not>
                <fes:PropertyIsNull>
                    <fes:ValueReference>location</fes:ValueReference>
                </fes:PropertyIsNull>
            </fes:Not>
        </fes:Filter>""",
        2,
    ),
    (
        "equal",
        Url.COMPLEX,
        """
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
    ),
    (
        "equal_xmlns",
        Url.COMPLEX,
        """
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
    ),
    (
        "equal_functions",
        Url.NORMAL,
        """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:Function name="strToLowerCase">
                    <fes:Function name="strSubstring">
                        <fes:ValueReference>name</fes:ValueReference>
                        <fes:Literal>0</fes:Literal>
                        <fes:Literal>3</fes:Literal>
                    </fes:Function>
                </fes:Function>
                <fes:Literal>caf</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    ),
    (
        "strIndexOf",
        Url.NORMAL,
        """
        <?xml version="1.0"?>
        <fes:Filter
             xmlns:fes="http://www.opengis.net/fes/2.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://www.opengis.net/fes/2.0
             http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:Function name="strIndexOf">
                    <fes:ValueReference>name</fes:ValueReference>
                    <fes:Literal>af</fes:Literal>
                </fes:Function>
                <fes:Literal>1</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>""",
    ),
    (
        "not_nil_child",
        Url.COMPLEX,
        """
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
    ),
    (
        "not_nil_flat",
        Url.FLAT,
        """
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
    ),
    (
        "m2m",
        Url.COMPLEX,
        """
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
    ),
    (
        "equal",
        Url.FLAT,
        """
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
    ),
    (
        "equal_xmlns",
        Url.FLAT,
        """
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
    ),
]

# Invalid Filters with their respective GET and POST request exceptions.
INVALID_FILTERS = {
    "syntax": (
        """<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">FDFDS</fes:Filter""",
        OperationParsingFailed(
            "Unable to parse FILTER argument: unclosed token:",
            locator="filter",
        ),
        OperationParsingFailed(
            "Unable to parse XML: not well-formed (invalid token):",
            locator="filter",
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
            "Unable to parse FILTER argument: unbound prefix:",
            locator="filter",
        ),
        OperationParsingFailed(
            "Unable to parse XML: unbound prefix:",
            locator="filter",
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
            "Unable to parse FILTER argument: mismatched tag:",
            locator="filter",
        ),
        OperationParsingFailed(
            "Unable to parse XML: mismatched tag:",
            locator="filter",
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
            "Invalid data for the 'rating' property: Can't cast 'TEXT' to double.",
            locator="filter",
        ),
        None,
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
            "Operator '{http://www.opengis.net/fes/2.0}PropertyIsLike'"
            " is not supported for the 'rating' property.",
            locator="filter",
        ),
        None,
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
            "Invalid data for the 'created' property:"
            " Date must be in YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format.",
            locator="filter",
        ),
        None,
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
            "Invalid data for the 'created' property:"
            " Date must be in YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format.",
            locator="filter",
        ),
        None,
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
            "Operator '{http://www.opengis.net/fes/2.0}PropertyIsLessThanOrEqualTo'"
            " does not support comparing geometry properties: '{http://www.opengis.net/gml/3.2}boundedBy'.",
            locator="filter",
        ),
        None,
    ),
}

GENERATED_FIELD_FILTER = {
    "name_reversed": (
        """
        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xsi:schemaLocation="http://www.opengis.net/fes/2.0
                http://schemas.opengis.net/filter/2.0/filterAll.xsd">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>name_reversed</fes:ValueReference>
                <fes:Literal>emordnilaP</fes:Literal>
            </fes:PropertyIsEqualTo>
        </fes:Filter>
        """
    ),
    "geometry_translated": (
        # geometry_translated =~ 5.90876 53.36317
        """
        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:BBOX>
                <fes:ValueReference>geometry_translated</fes:ValueReference>
                <gml:Envelope xmlns:gml="http://www.opengis.net/gml/3.2"
                              srsName="urn:ogc:def:crs:EPSG::4326">
                    <gml:lowerCorner>53.1 5.7</gml:lowerCorner>
                    <gml:upperCorner>53.5 6.1</gml:upperCorner>
                </gml:Envelope>
            </fes:BBOX>
        </fes:Filter>
        """
    ),
}

# Of the form (name, type, sort_by, expect)
SORT_BY = [
    ("name", Url.NORMAL, "name", ["Café Noir", "Foo Bar"]),
    ("name-a", Url.NORMAL, "name A", ["Café Noir", "Foo Bar"]),
    ("name-asc", Url.NORMAL, "name ASC", ["Café Noir", "Foo Bar"]),
    ("name-d", Url.NORMAL, "name D", ["Foo Bar", "Café Noir"]),
    ("name-desc", Url.NORMAL, "name DESC", ["Foo Bar", "Café Noir"]),
    ("rating-desc", Url.NORMAL, "rating DESC", ["Café Noir", "Foo Bar"]),
    ("rating,name-asc", Url.NORMAL, "rating,name ASC", ["Foo Bar", "Café Noir"]),
    ("city/name", Url.COMPLEX, "city/name", ["Café Noir", "Foo Bar"]),
    ("city/name-desc", Url.COMPLEX, "city/name DESC", ["Foo Bar", "Café Noir"]),
    ("city-name", Url.FLAT, "city-name", ["Café Noir", "Foo Bar"]),
    ("city-name-desc", Url.FLAT, "city-name DESC", ["Foo Bar", "Café Noir"]),
]

SORT_BY_XML = [
    (
        "name",
        Url.NORMAL,
        """
        <fes:SortProperty>
            <fes:ValueReference>name</fes:ValueReference>
        </fes:SortProperty>
        """,
        ["Café Noir", "Foo Bar"],
    ),
    (
        "name-asc",
        Url.NORMAL,
        """
        <fes:SortProperty>
            <fes:ValueReference>name</fes:ValueReference>
            <fes:SortOrder>ASC</fes:SortOrder>
        </fes:SortProperty>
        """,
        ["Café Noir", "Foo Bar"],
    ),
    (
        "name-desc",
        Url.NORMAL,
        """
        <fes:SortProperty>
            <fes:ValueReference>name</fes:ValueReference>
            <fes:SortOrder>DESC</fes:SortOrder>
        </fes:SortProperty>
        """,
        ["Foo Bar", "Café Noir"],
    ),
    (
        "rating-desc",
        Url.NORMAL,
        """
        <fes:SortProperty>
            <fes:ValueReference>rating</fes:ValueReference>
            <fes:SortOrder>DESC</fes:SortOrder>
        </fes:SortProperty>
        """,
        ["Café Noir", "Foo Bar"],
    ),
    (
        "city-name",
        Url.FLAT,
        """
        <fes:SortProperty>
            <fes:ValueReference>city-name</fes:ValueReference>
        </fes:SortProperty>
        """,
        ["Café Noir", "Foo Bar"],
    ),
    (
        "city-name-desc",
        Url.FLAT,
        """
        <fes:SortProperty>
            <fes:ValueReference>city-name</fes:ValueReference>
            <fes:SortOrder>DESC</fes:SortOrder>
        </fes:SortProperty>
        """,
        ["Foo Bar", "Café Noir"],
    ),
    (
        "city/name",
        Url.COMPLEX,
        """
        <fes:SortProperty>
            <fes:ValueReference>city/name</fes:ValueReference>
        </fes:SortProperty>
        """,
        ["Café Noir", "Foo Bar"],
    ),
    (
        "city/name-desc",
        Url.COMPLEX,
        """
        <fes:SortProperty>
            <fes:ValueReference>city/name</fes:ValueReference>
            <fes:SortOrder>DESC</fes:SortOrder>
        </fes:SortProperty>
        """,
        ["Foo Bar", "Café Noir"],
    ),
    (
        "rating,name-asc",
        Url.NORMAL,
        """
        <fes:SortProperty>
            <fes:ValueReference>rating</fes:ValueReference>
            <fes:SortOrder>ASC</fes:SortOrder>
        </fes:SortProperty>
        <fes:SortProperty>
            <fes:ValueReference>name</fes:ValueReference>
            <fes:SortOrder>ASC</fes:SortOrder>
        </fes:SortProperty>
        """,
        ["Foo Bar", "Café Noir"],
    ),
]
