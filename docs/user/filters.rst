Accessing WFS Data
==================

This is a brief explanation of using a WFS server.

.. contents:: :local:

Using GIS Software
------------------

Commonly, a WFS server can is accessed by GIS-software, such as `QGis <https://qgis.org/>`_.
The URL that's configured inside ``urls.py`` can be used directly as WFS endpoint.
For example, add https://api.data.amsterdam.nl/v1/wfs/gebieden/ to QGis.

Everything, for querying and viewing can be done in QGis.

.. tip::
    The parameters ``?SERVICE=WFS&VERSION=2.0.0&REQUEST=..`` are appended to the URL
    by QGis. It's not required to add these yourself.

Manual Access
-------------

The WFS server can also be accessed directly from a HTTP client (e.g. curl) or web browser.
In such case, use the basic URL above, and include the query parameters:

:samp:`?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES={featurename}`

The available feature types can be found in the **GetCapabilities** request:

``?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities``

The remaining part of this page assumes this manual access.

Tuning the Results
------------------

Export Formats
~~~~~~~~~~~~~~

The following export formats are available:

* GeoJSON
* CSV

These can be queried by manually crafting a **GetFeature** request.
The parameters :samp:`TYPENAMES={feature-name}` and :samp:`OUTPUTFORMAT={format}` should be included.

For example:

* `...&TYPENAMES=wijken&OUTPUTFORMAT=geojson <https://api.data.amsterdam.nl/v1/wfs/gebieden/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=geojson>`_
* `...&TYPENAMES=wijken&OUTPUTFORMAT=csv <https://api.data.amsterdam.nl/v1/wfs/gebieden/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=csv>`_

.. tip::
   In the example links above, a ``COUNT=`` parameter is included to activate pagination.
   When this parameter is omitted, *all objects* will be returned in a single request.
   For most datasets, the server is capable of efficiently delivering all results in a single response.

Reducing Returned Fields
~~~~~~~~~~~~~~~~~~~~~~~~

The ``PROPERTYNAME`` parameter can be used to define which elements should be returned.

For example:

* `...&PROPERTYNAME=app:naam,app:code <https://api.data.amsterdam.nl/v1/wfs/gebieden/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&PROPERTYNAME=app:naam,app:code>`_
* `...&PROPERTYNAME=app:naam,app:code&OUTPUTFORMAT=geojson <https://api.data.amsterdam.nl/v1/wfs/gebieden/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&PROPERTYNAME=app:naam,app:code&OUTPUTFORMAT=geojson>`_

.. tip::

    This project also supports using ``PROPERTYNAME`` for nested elements (:samp:`{parent}/{child}`).
    The WFS 2.0 specification defines the ``PROPERTYNAME`` as a QName for top-level elements only.


Changing Geometry Projections
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The exportlink can be extended with the ``SRSNAME`` parameter to define the geometry projection
of all geo data. For example, ``SRSNAME=urn:ogc:def:crs:EPSG::3857`` activates the web-mercator projection
which is used by Google Maps. A common default is ``urn:ogc:def:crs:EPSG::4326``, which is the
worldwide WGS 84 longitude-latitude.

Filtering Results
-----------------

Simple Filters
~~~~~~~~~~~~~~

The WFS protocol offers a powerful syntax to filter data.
Use the request ``REQUEST=GetFeature`` with a ``FILTER`` argument.
The filter value is expressed as XML.

For example, to query all neighbourhoods (typename buurten) of the central district (stadsdeel) in Amsterdam:

.. code-block:: xml

    <Filter>
        <PropertyIsEqualTo>
            <ValueReference>ligt_in_stadsdeel/naam</ValueReference>
            <Literal>Centrum</Literal>
        </PropertyIsEqualTo>
    </Filter>

This can be included in the request, for example:

* `...&TYPENAMES=wijken&OUTPUTFORMAT=geojson&FILTER=%3CFilter%3E%3CPropertyIsEqualTo%3E%3CValueReference... <https://api.data.amsterdam.nl/v1/wfs/gebieden/?expand=ligt_in_stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=geojson&FILTER=%3CFilter%3E%3CPropertyIsEqualTo%3E%3CValueReference%3Eligt_in_stadsdeel/naam%3C/ValueReference%3E%3CLiteral%3ECentrum%3C/Literal%3E%3C/PropertyIsEqualTo%3E%3C/Filter%3E>`_

The ``FILTER`` parameter replaces the separate ``BBOX`` and ``RESOURCEID`` parameters.
If you use these parameters as well, they should be included in the filter:

.. code-block:: xml

    <Filter>
        <And>
            <BBOX>
                <gml:Envelope srsName="EPSG:4326">
                    <gml:lowerCorner>4.58565 52.03560</gml:lowerCorner>
                    <gml:upperCorner>5.31360 52.48769</gml:upperCorner>
                </gml:Envelope>
            </BBOX>
            <PropertyIsEqualTo>
                <ValueReference>status</ValueReference>
                <Literal>1</Literal>
            </PropertyIsEqualTo>
        </And>
    </Filter>

The ``RESOURCEID`` parameter has a ``<ResourceId>`` equivalent which can appear several times in the filter:

.. code-block:: xml

    <Filter>
        <ResourceId rid="TYPENAME.123" />
        <ResourceId rid="TYPENAME.4325" />
        <ResourceId rid="OTHERTYPE.567" />
    </Filter>


Complex Filters
~~~~~~~~~~~~~~~

The WFS Filter Encoding Standaard (FES) supports many operators.
These tags are all supported:

.. list-table::
   :header-rows: 1

   * - Element
     - SQL equivalent
     - Description
   * - ``<PropertyIsEqualTo>``
     - :samp:`{a} == {b}`
     - Values must be equal.
   * - ``<PropertyIsNotEqualTo>``
     - :samp:`{a} != {b}`
     - Values must not be equal.
   * - ``<PropertyIsLessThan>``
     - :samp:`{a} < {b}`
     - Value 1 must be less than value 2.
   * - ``<PropertyIsGreaterThan>``
     - :samp:`{a} > {b}`
     - Value 1 must be greater than value 2.
   * - ``<PropertyIsLessThanOrEqualTo>``
     - :samp:`{a} <= {b}`
     - Value 1 must be less than or equal to value 2.
   * - ``<PropertyIsGreaterThanOrEqualTo>``
     - :samp:`{a} >= {b}`
     - Value 1 must be greater than or equal to value 2.
   * - ``<PropertyIsBetween>``
     - :samp:`{a} BETWEEN {x} AND {y}`
     - Compares between ``<LowerBoundary>`` and ``<UpperBoundary>``,
       which both contain an expression.
   * - ``<PropertyIsLike>``
     - :samp:`{a} LIKE {b}`
     - Performs a wildcard comparison.
   * - ``<PropertyIsNil>``
     - :samp:`{a} IS NULL`
     - Value must be ``NULL`` (``xsi:nil="true"`` in XML).
   * - ``<PropertyIsNull>``
     - n.a.
     - Property may not exist (currently implemented as ``<PropertyIsNil>``).
   * - ``<BBOX>``
     - :samp:`ST_Intersects({a}, {b})`
     - Geometry must be partly in value 2. The field name may be omitted to use the default.
   * - ``<Contains>``
     - :samp:`ST_Contains({a}, {b})`
     - Geometry completely contains geometry 2, e.g. province contains city.
   * - ``<Crosses>``
     - :samp:`ST_Crosses({a}, {b})`
     - The geometries have some common interior points, e.g. two streets.
   * - ``<Disjoint>``
     - :samp:`ST_Disjoint({a}, {b})`
     - The geometries are not connected in any way.
   * - ``<Equals>``
     - :samp:`ST_Equals({a}, {b})`
     - The geometries are identical.
   * - ``<Intersects>``
     - :samp:`ST_Intersects({a}, {b})`
     - The geometries share some space.
   * - ``<Touches>``
     - :samp:`ST_Touches({a}, {b})`
     - The edges of the geometries touch each other, e.g. country borders.
   * - ``<Overlaps>``
     - :samp:`ST_Overlaps({a}, {b})`
     - The geometries overlap.
   * - ``<Within>``
     - :samp:`ST_Within({a}, {b})`
     - Geometry is completely contained within geometry 2, e.g. city within province.
   * - ``<DWithin>``
     - :samp:`ST_DWithin({a}, {b}, {d})`
     - The geometries are within a given distance of each other.
   * - ``<Beyond>``
     - :samp:`NOT ST_DWithin({a}, {b}, {d})`
     - The geometries are not within a given distance.
   * - ``<And>``
     - :samp:`{a} AND {b} AND {c}`
     - The nested operators must all be true.
   * - ``<Or>``
     - :samp:`{a} OR {b} OR {c}`
     - Only one of the nested operators has to be true.
   * - ``<Not>``
     - :samp:`NOT {a}`
     - Negation of the nested operators.
   * - ``<ResourceId>``
     - :samp:`table.id == {value}` / :samp:`table.id IN ({v1}, {v2}, ...)`
     - Searches for a feature as "type name.identifier".
       Combines multiple elements into an ``IN`` query.

.. tip::
   For the ``<BBOX>`` operator the geometry field may be omitted.
   The standard geometry field is then used as configured in the feature type.

.. note::
   Although a number of geometry operators seem to be identical for surfaces
   (such as ``<Intersects>``, ``<Crosses>`` and ``<Overlaps>``),
   their mutual differences are particularly visible when comparing points with surfaces.

Expressions in the Filter
~~~~~~~~~~~~~~~~~~~~~~~~~

Various expressions may be used as values:

.. list-table::
   :header-rows: 1

   * - Expression
     - SQL equivalent
     - Description
   * - ``<ValueReference>``
     - :samp:`"{field-name}"`
     - References a field.
   * - ``<Literal>``
     - value
     - Literal value, can also be a GML-object.
   * - ``<Function>``
     - :samp:`{function-name}(..)`
     - Executes a function, such as ``abs``, ``sin``, ``strLength``.
   * - ``<Add>``
     - :samp:`{a} + {b}`
     - Addition (WFS 1 expression).
   * - ``<Sub>``
     - :samp:`{a} - {b}`
     - Subtraction (WFS 1 expression).
   * - ``<Mul>``
     - :samp:`{a} * {b}`
     - Multiplication (WFS 1 expression).
   * - ``<Div>``
     - :samp:`{a} / {b}`
     - Division (WFS 1 expression).

This allows to create complex filters, such as:

.. code-block:: xml

    <Filter>
        <And>
            <PropertyIsEqualTo>
                <ValueReference>status</ValueReference>
                <Literal>1</Literal>
            </PropertyIsEqualTo>
            <Or>
                <PropertyIsEqualTo>
                    <ValueReference>container_type</ValueReference>
                    <Literal>Other</Literal>
                </PropertyIsEqualTo>
                <PropertyIsEqualTo>
                    <ValueReference>container_type</ValueReference>
                    <Literal>Textile</Literal>
                </PropertyIsEqualTo>
                <PropertyIsEqualTo>
                    <ValueReference>container_type</ValueReference>
                    <Literal>Glass</Literal>
                </PropertyIsEqualTo>
                <PropertyIsEqualTo>
                    <ValueReference>container_type</ValueReference>
                    <Literal>Papier</Literal>
                </PropertyIsEqualTo>
                <PropertyIsEqualTo>
                    <ValueReference>container_type</ValueReference>
                    <Literal>Organic</Literal>
                </PropertyIsEqualTo>
                <PropertyIsEqualTo>
                    <ValueReference>container_type</ValueReference>
                    <Literal>Plastic</Literal>
                </PropertyIsEqualTo>
            </Or>
        </And>
    </Filter>

.. _functions:

Using Functions
~~~~~~~~~~~~~~~

Functions are executed in a ``<Filter>`` by using the tag ``<Function name="..">..</Function>``.
This can be used anywhere as an expression instead of a ``<ValueReference>`` or ``<Literal>``.

Inside the function, the parameters are also given as expressions:
a ``<ValueReference>``, ``<Literal>`` or new ``<Function>``.
As a simple example:

.. code-block:: xml

    <fes:Function name="sin">
        <fes:ValueReference>fieldname</fes:ValueReference>
    </fes:Function>

As expressions can be functions, the following filter is possible:

.. code-block:: xml

    <Filter>
        <PropertyIsEqualTo>
            <Function name="strToLowerCase">
                <Function name="strSubstring">
                    <ValueReference>name</ValueReference>
                    <Literal>0</Literal>
                    <Literal>4</Literal>
                </Function>
            </Function>
            <Literal>cafe</Literal>
        </PropertyIsEqualTo>
    </Filter>

Various functions are built-in available in the server, inspired by the filter functions found
in `GeoServer <https://docs.geoserver.org/stable/en/user/filter/function_reference.html>`_:

.. list-table:: String Functions
   :header-rows: 1
   :widths: 40 30 30

   * - Function
     - SQL equivalent
     - Description
   * - ``strConcat(string)``
     - ``CONCAT()``
     - Concatenates strings
   * - ``strIndexOf(string, substring)``
     - ``STRPOS() - 1``
     - Finds the text inside a string, 0-based index.
   * - ``strSubstring(string, begin, end)``
     - ``SUBSTRING()``
     - Removes characters before *begin* and after *end*.
   * - ``strSubstringStart(string, begin)``
     - ``SUBSTRING()``
     - Removes characters before *begin*, 0-based index.
   * - ``strToLowerCase(string)``
     - ``LOWER()``
     - Convert text to lowercase.
   * - ``strToUpperCase(string)``
     - ``UPPER()``
     - Convert text to uppercase.
   * - ``strTrim(string)``
     - ``TRIM()``
     - Remove white space at the beginning and end.
   * - ``strLength(string)``
     - ``LENGTH()`` / ``CHAR_LENGTH()``
     - Determines text length.
   * - ``length(string)``
     - ``LENGTH()`` / ``CHAR_LENGTH()``
     - Alias of ``strLength()``.

.. list-table:: Math Number Functions
   :header-rows: 1
   :widths: 40 30 30

   * - Function
     - SQL equivalent
     - Description
   * - ``abs(number)``
     - ``ABS()``
     - Invert negative numbers.
   * - ``ceil(number)``
     - ``CEIL()``
     - Rounding up.
   * - ``floor(number)``
     - ``FLOOR()``
     - Rounding down.
   * - ``round(value)``
     - ``ROUND()``
     - Regular rounding.
   * - ``min(value1, value2)``
     - ``LEAST()``
     - Uses the smallest number.
   * - ``max(value1, value2)``
     - ``GREATEST()``
     - Uses the largest number.
   * - ``pow(base, exponent)``
     - ``POWER()``
     - Exponentiation
   * - ``exp(value)``
     - ``EXP()``
     - Exponent of 𝑒 (2,71828...; natural logarithm).
   * - ``log(value)``
     - ``LOG()``
     - Logarithm; inverse of an exponent.
   * - ``sqrt(value)``
     - ``SQRT()``
     - Square root, inverse of exponentiation.

.. list-table:: Math Trigonometry Functions
   :header-rows: 1
   :widths: 40 30 30

   * - Function
     - SQL equivalent
     - Description
   * - ``acos(value)``
     - ``ACOS()``
     - Arccosine; inverse of cosine.
   * - ``asin(value)``
     - ``ASIN()``
     - Arcsine; inverse van sine.
   * - ``atan(value)``
     - ``ATAN()``
     - Arctangent; inverse of tangent.
   * - ``atan2(x, y)``
     - ``ATAN2()``
     - Arctangent, for usage outside the range of a circle.
   * - ``cos(radians)``
     - ``COS()``
     - Cosine
   * - ``sin(radians)``
     - ``SIN()``
     - Sine
   * - ``tan(radians)``
     - ``TAN()``
     - Tangent
   * - ``pi()``
     - ``PI``
     - The value of π (3,141592653...)
   * - ``toDegrees(radians)``
     - ``DEGREES()``
     - Conversion of radians to degrees.
   * - ``toRadians(degree)``
     - ``RADIANS()``
     - Conversion degrees to radians.

.. list-table:: Geometric Functions
   :header-rows: 1

   * - Function
     - SQL equivalent
     - Description

   * - ``area(geometry)``
     - ``ST_Area()``
     - Convert geometry to area.
   * - ``centroid(features)``
     - ``ST_Centroid()``
     - Return geometric center as "gravity point".
   * - ``difference(geometry1, geometry2)``
     - ``ST_Difference()``
     - Parts of geometry 1 that do not overlap with geometry 2.
   * - ``distance(geometry1, geometry2)``
     - ``ST_Distance()``
     - Minimum distance between 2 geometries.
   * - ``envelope(geometry)``
     - ``ST_Envelope()``
     - Convert geometry to bounding box.
   * - ``geomLength(geometry)``
     - ``ST_Length()``
     - The cartesian length for a linestring/curve.
   * - ``intersection(geometry1, geometry2)``
     - ``ST_Intersection()``
     - Parts of geometry 1 that overlap with geometry 2.
   * - ``isEmpty(geometry)``
     - ``ST_IsEmpty()``
     - Tests whether the geometry is empty.
   * - ``isValid(geometry)``
     - ``ST_IsValid()``
     - Tests whether the geometry is valid.
   * - ``numGeometries(geometry)``
     - ``ST_NumGeometries()``
     - Tests how many geometries are found in the collection.
   * - ``numPoints(geometry)``
     - ``ST_NumPoints()``
     - Tests how many points are found in a linestring.
   * - ``perimeter(geometry)``
     - ``ST_Perimeter()``
     - The 2D perimeter of the surface/polygon.
   * - ``symDifference(geometry1, geometry1)``
     - ``ST_SymDifference()``
     - Parts of geometry 1 and 2 that don't intersect.
   * - ``union(geometry1, geometry2)``
     - ``ST_Union()``
     - Merge Geometry 1 and 2.


Using XML POST Requests
-----------------------

When the filter length exceeds the query-string limits,
consider using an XML POST request instead of the KVP query-string format.

A GET request such as:

.. code-block:: urlencoded

    ?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature
    &TYPENAMES=app:restaurant
    &FILTER=<Filter>...</Filter>
    &PROPERTYNAME=app:id,app:name,app:location
    &SORTBY=app:name ASC

...can also be defined as XML-encoded POST request:

.. code-block:: xml

    <wfs:GetFeature service="WFS" version="2.0.0"
        xmlns:wfs="http://www.opengis.net/wfs/2.0"
        xmlns:gml="http://www.opengis.net/gml/3.2"
        xmlns:fes="http://www.opengis.net/fes/2.0"
        xmlns:app="http://example.org/my-namespace">

      <wfs:Query typeNames="app:restaurant">
        <wfs:PropertyName>app:id</wfs:PropertyName>
        <wfs:PropertyName>app:name</wfs:PropertyName>
        <wfs:PropertyName>app:location</wfs:PropertyName>

        <fes:Filter>
          ...
        </fes:Filter>

        <fes:SortBy>
          <fes:SortProperty>
            <fes:ValueReference>app:name</fes:ValueReference>
            <fes:SortOrder>ASC</fes:SortOrder>
          </fes:SortProperty>
        </fes:SortBy>
      </wfs:Query>
    </wfs:GetFeature>


Support for Older Clients
-------------------------

Missing XML Namespaces
~~~~~~~~~~~~~~~~~~~~~~

Strictly speaking, XML namespaces are required in the filter. Since many clients omit them,
the server also supports requests without namespaces. For the sake of completeness,
a request with namespaces included looks like this:

.. code-block:: xml

    <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xsi:schemaLocation="http://www.opengis.net/fes/2.0
            http://schemas.opengis.net/filter/2.0/filterAll.xsd">
        <fes:PropertyIsEqualTo>
            <fes:ValueReference>stadsdeel/naam</fes:ValueReference>
            <fes:Literal>Centrum</fes:Literal>
        </fes:PropertyIsEqualTo>
    </fes:Filter>

When a geometry filter is included, this also requires the GML namespace:

.. code-block:: xml

    <fes:Filter
        xmlns:fes="http://www.opengis.net/fes/2.0"
        xmlns:gml="http://www.opengis.net/gml/3.2"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.opengis.net/fes/2.0
        http://schemas.opengis.net/filter/2.0/filterAll.xsd
        http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd">
        <fes:BBOX>
            <gml:Polygon gml:id="P1" srsName="http://www.opengis.net/def/crs/epsg/0/4326">
                <gml:exterior>
                    <gml:LinearRing>
                        <gml:posList>10 10 20 20 30 30 40 40 10 10</gml:posList>
                    </gml:LinearRing>
                </gml:exterior>
            </gml:Polygon>
        </fes:BBOX>
    </fes:Filter>

According to the XML rules, the "fes" namespace alias can be renamed here
or omitted if only ``xmlns="..."`` is used instead of ``xmlns:fes="..."``.

Older Filter Syntax
~~~~~~~~~~~~~~~~~~~

Several existing clients still use other WFS 1 elements, such as ``<PropertyName>`` instead of
of ``<ValueReference>``. For compatibility this tag is also supported.

The WFS 1 expressions ``<Add>``, ``<Sub>``, ``<Mul>`` and ``<Div>`` are also implemented
to support arithmetic operations from QGis (addition, subtraction, multiplication and division).
