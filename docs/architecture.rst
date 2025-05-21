.. _architecture:

Internal Architecture
=====================

.. contents:: :local:

When you follow the source of the ``WFSView``, ``WFSOperation`` and ``BaseOwsRequest`` classes,
you'll find that it's written with extensibility in mind.
Extra operations can easily be added there.
You could even do that within your own projects and implementations.

A lot of the internal classes and object names are direct copies from
the :ref:`WFS 2.0 specification <wfs-spec>`.
By following these type definitions, a lot of the logic and code structure follows naturally.

Features and Fields
-------------------

Each :class:`~gisserver.features.FeatureField` is transformed into
an internal :class:`~gisserver.types.XsdElement` object. The model field access happens
through :meth:`~gisserver.types.XsdNode.get_value`.
Note that the ``type`` can either reference either
an :class:`~gisserver.types.XsdTypes` value or :class:`~gisserver.types.XsdComplexType` object.

.. graphviz::

    digraph foo {
        rankdir = LR;

        FeatureField [shape=box]
        XsdElement [shape=box]
        type [shape=none, label=".type"]
        model_attribute [shape=none, label=".model_attribute"]
        get_value [shape=none, label=".get_value(instance)"]

        FeatureField -> XsdElement [label=".xsd_element"]
        XsdElement -> model_attribute
        XsdElement -> type
        XsdElement -> get_value
    }

Each :class:`~gisserver.features.FeatureType` is transformed into
an internal :class:`~gisserver.types.XsdComplexType` definition:

.. graphviz::

    digraph foo {
        rankdir = LR;

        FeatureType [shape=box]
        FeatureField [shape=box]
        XsdComplexType [shape=box]
        XsdElement [shape=box]
        XsdAttribute [shape=box]

        FeatureType -> FeatureField [label=".fields"]
        FeatureType -> XsdComplexType [label=".xsd_type"]
        XsdComplexType -> XsdElement [label=".elements"]
        XsdComplexType -> XsdAttribute [label=".attributes"]
    }

Every bit of the internal logic walks through the internal XSD structure.
This includes:

* Rendering GML/GeoJSON/CSV output.
* Rendering the XML schema.
* Resolving filter expressions.
* Applying rendering projections.

Request Processing
------------------

To handle a request, several things happen:

* Request parsing.
* Query construction.
* Query execution.
* Output rendering.

To summarize:

.. graphviz::

    digraph foo {
        rankdir = LR;
        node [shape=box]

        WFSView [label="WFSView"]
        parsing [label="gisserver.parsers.wfs20"]
        operations [label="gisserver.operations.wfs20"]
        validate_request [label=".validate_request()", shape=none]
        process_request [label=".process_request()", shape=none]
        getdata [label="retrieve data...", shape=none]

        WFSView -> parsing
        WFSView -> operations
        operations -> validate_request
        operations -> process_request
        process_request -> getdata

        rendering [label="gisserver.output"]
        process_request -> rendering
    }

Parsing the Request
~~~~~~~~~~~~~~~~~~~

The incoming XML POST message (e.g. a ``<wfs:GetFeature>`` request)
is translated as an internal "Abstract Syntax Tree" (AST)
which closely resembles all class names that the WFS and FES standards define.
This happens in :mod:`gisserver.parsers`.

The GET parameters are treated as Key-Value-Pairs (KVP).
This is treated as a special case of the fully
supported request notation that XML POST provides.

A GET request such as:

.. code-block:: urlencoded

    ?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature
    &TYPENAMES=app:restaurant
    &FILTER=<Filter>...</Filter>
    &PROPERTYNAME=app:id,app:name,app:location
    &SORTBY=app:name ASC

or an XML-encoded request such as:

.. code-block:: xml

    <wfs:GetFeature service="WFS" version="2.0.0" xmlns:wfs="..."
        xmlns:gml="..." xmlns:fes="..." xmlns:app="...">

      <wfs:Query typeNames="app:restaurant">
        <wfs:PropertyName>app:id</wfs:PropertyName>
        <wfs:PropertyName>app:name</wfs:PropertyName>
        <wfs:PropertyName>app:location</wfs:PropertyName>

        <fes:Filter>
          <fes:And>
            <fes:BBOX>
              <gml:Envelope srsName="urn:ogc:def:crs:EPSG::28992">
                <gml:lowerCorner>122400 486200</gml:lowerCorner>
                <gml:upperCorner>122500 486300</gml:upperCorner>
              </gml:Envelope>
            </fes:BBOX>

            <fes:PropertyIsGreaterThanOrEqualTo>
              <fes:ValueReference>app:rating</fes:ValueReference>
              <fes:Literal>3.0</fes:Literal>
            </fes:PropertyIsGreaterThanOrEqualTo>
          </fes:And>
        </fes:Filter>

        <fes:SortBy>
          <fes:SortProperty>
            <fes:ValueReference>app:name</fes:ValueReference>
            <fes:SortOrder>ASC</fes:SortOrder>
          </fes:SortProperty>
        </fes:SortBy>
      </wfs:Query>

      <wfs:StoredQuery id="urn:ogc:def:query:OGC-WFS::GetFeatureById">
        <wfs:Parameter name="ID">restaurant.123</wfs:Parameter>
      </wfs:StoredQuery>
    </wfs:GetFeature>

gives an AST somewhat like:

.. graphviz::

    digraph foo {
        node [shape=box]

        GetFeature [label="GetFeature\n<wfs:GetFeature>"]

        GetFeature -> QueryExpression [label=".queries[...]"]
        QueryExpression -> AdhocQuery [dir=back arrowtail=empty]

        AdhocQuery [label="AdhocQuery\n<wfs:Query>"]
        StoredQuery [label="StoredQuery\n<wfs:StoredQuery>"]
        PropertyName [label="PropertyName\n<wfs:PropertyName>"]
        Filter [label="Filter\n<fes:Filter>"]
        SortBy [label="SortBy\n<fes:SortBy>"]

        AdhocQuery -> PropertyName [label=".property_names"]
        AdhocQuery -> Filter [label=".filter"]
        AdhocQuery -> SortBy [label=".sortBy"]

        BinaryLogicOperator [label="BinaryLogicOperator\n<fes:And>"]
        BinarySpatialOperator [label="BinarySpatialOperator\n<fes:BBOX>"]
        BinaryComparisonOperator [label="BinaryComparisonOperator\n<fes:PropertyIsEqualTo>"]
        Envelope [label="Envelope\n<gml:Envelope>"]
        ValueReference [label="ValueReference\n<fes:ValueReference>"]
        Literal [label="Literal\n<fes:Literal>"]

        Filter -> BinaryLogicOperator [label=".predicate"]
        BinaryLogicOperator -> BinarySpatialOperator
        BinaryLogicOperator -> BinaryComparisonOperator [label=".operands[...]"]
        BinarySpatialOperator -> Envelope [label=".operand2"]
        BinaryComparisonOperator -> ValueReference [label=".expression[0]"]
        BinaryComparisonOperator -> Literal [label=".expression[1]"]

        ValueReference2 [label="ValueReference\n<fes:ValueReference>"]
        SortProperty [label="SortProperty\n<fes:SortProperty>"]
        SortOrder [label="SortOrder\n<fes:SortOrder>"]

        SortBy -> SortProperty
        SortProperty -> ValueReference2
        SortProperty -> SortOrder

        QueryExpression -> StoredQuery [dir=back arrowtail=empty]
        StoredQuery -> StoredQueryImplementation [label=".implementation"]

        GetFeatureById
        custom [label="..."]
        StoredQueryImplementation -> GetFeatureById [dir=back arrowtail=empty]
        StoredQueryImplementation -> custom [dir=back arrowtail=empty]
    }

The top-level request parsing classes provide a ``from_xml()`` and ``from_kvp_request()`` classmethod.
This allows the initialization of these objects from the XML POST or KVP GET formats respectively.

The filter classes typically have a ``from_xml()`` only,
as the filter syntax is always written in XML.

All regular requests parameters such as ``?FILTER=...``, ``?BBOX=...``, ``?SORTBY=...``
and ``?RESOURCEID=...`` are processed by the ``AdhocQuery`` class.

The ``StoredQuery`` node is used for ``?STOREDQUERY_ID=...`` and ``<wfs:StoredQuery>`` requests.

.. note::
    All the class names in this AST are mentioned in the WFS, FES and GML specifications.
    They are also found in the corresponding XSD schema.

    The rare exception would be the ``AdhocQuery`` type, which is used for
    `<wfs:Query> <https://www.mediamaps.ch/ogc/schemas-xsdoc/sld/1.2/wfs_xsd.html#Query>`_ element.
    The spec extends it from ``fes:AbstractAdhocQueryExpression`` and ``fes:QueryExpression``.

Dealing With Inheritance
........................

Note most filter arguments support many different tags. The specification
defines the arguments as an :class:`~gisserver.parsers.fes20.expressions.Expression`
or :class:`~gisserver.parsers.fes20.operators.NonIdOperator` subclass.
For example, ``<fes:PropertyIsEqualTo>`` accepts
both ``<fes:ValueReference>``, ``<fes:Literal>`` or ``<fes:Function>``.
The code solves this by calling ``Expression.child_from_xml()``.
It will resolve the correct child parsing class based on the tag name.

Query Construction
~~~~~~~~~~~~~~~~~~

This parsed request is passed to the corresponding operation, which handles that request type.
For the :class:`gisserver.parsers.wfs20.GetFeature` request,
there is a :class:`gisserver.operations.wfs20.GetFeature` operation.

The ``GetFeature`` and ``GetPropertyValue`` operations will use the AST tree
to turn the query into a Django ``QuerySet``.
This ``QuerySet`` becomes part of the ``FeatureCollection`` for rendering.

.. graphviz::

    digraph foo {

        GetFeature [shape=box]
        QueryExpression [shape=box]
        FeatureCollection [shape=box]
        SimpleFeatureCollection [shape=box]
        validate_request [shape=none, label=".validate_request()", fontcolor="#1ba345"]
        process_request [shape=none, label=".process_request()", fontcolor="#1ba345"]
        get_results [shape=none, label=".get_results() / .get_hits()", fontcolor="#1ba345"]
        get_type_names [shape=none, label="query.get_type_names()", fontcolor="#1ba345"]
        get_queryset [shape=none, label=".get_queryset()", fontcolor="#1ba345"]
        build_query [shape=none, label=".build_query(compiler)", fontcolor="#1ba345"]
        compiler_get_queryset [shape=none, label="compiler.get_queryset()"]

        GetFeature -> validate_request
        GetFeature -> process_request
        validate_request -> get_type_names
        process_request -> get_results
        get_results -> QueryExpression

        QueryExpression -> get_queryset
        get_queryset -> build_query
        get_queryset -> compiler_get_queryset
        get_results -> FeatureCollection [rank=same]
        FeatureCollection -> SimpleFeatureCollection
    }

While walking through the AST, the :class:`~gisserver.parsers.query.CompiledQuery`
collects all intermediate data needed to translate the query to a Django ORM call.
As that object is passed though all nodes of the filter,
each ``build...()`` function can add their lookups and annotations.

It produces the ``QuerySet`` objects:

.. code-block:: python

    Restaurant.objects \
        .only('id', 'name', 'location')
        .filter(
            geometryfield__intersects=Polygon(...),
            rating__gte=3.0
        )

    Restaurant.objects.filter(pk=123)

The operation wraps all these ``QuerySet`` objects in a :class:`~gisserver.output.results.SimpleFeatureCollection` object.
All these collections become part of the final :class:`~gisserver.output.results.FeatureCollection`.

These collections attempt to use queryset-iterator logic as much as possible,
unless it would cause multiple queries (such as needing the ``number_matched`` data early).
This information can now be passed to the output rendering.

.. note::
    The names such as :class:`~gisserver.output.results.FeatureCollection`
    and :class:`~gisserver.output.results.SimpleFeatureCollection`
    all literally appear in the WFS 2.0 specification. They also correspond to the layout of the XML output.

Output Rendering
~~~~~~~~~~~~~~~~

Each :class:`~gisserver.operations.base.WFSOperation` has a list
of :class:`~gisserver.operations.base.OutputFormat` objects:

.. code-block:: python

    class GetFeature(BaseWFSGetDataOperation):

        def get_output_formats(self) -> list[OutputFormat]:
            return [
                OutputFormat("application/gml+xml", version="3.2", renderer_class=output.DBGML32Renderer),
                OutputFormat("text/xml", subtype="gml/3.2.1", renderer_class=output.DBGML32Renderer),
                OutputFormat("application/json", subtype="geojson", charset="utf-8", renderer_class=output.DBGeoJsonRenderer),
                OutputFormat("text/csv", subtype="csv", charset="utf-8", renderer_class=output.DBCSVRenderer),
                # OutputFormat("shapezip"),
                # OutputFormat("application/zip"),
            ]

The :class:`~gisserver.operations.base.OutputFormat` class may reference
an :attr:`~gisserver.operations.base.OutputFormat.renderer_class`
which points to an :class:`~gisserver.output.OutputRenderer`
(or :class:`~gisserver.output.CollectionOutputRenderer`) subclass.

.. graphviz::

    digraph foo {
        node [shape=box]

        WFSOperation -> OutputFormat [label=".get_output_formats()"]
        OutputFormat -> OutputRenderer [label=".renderer_class"]

        OutputRenderer -> XmlOutputRenderer [dir=back arrowtail=empty]
        OutputRenderer -> CollectionOutputRenderer [dir=back arrowtail=empty]

        XmlOutputRenderer -> XmlSchemaRenderer [dir=back arrowtail=empty]
        XmlOutputRenderer -> ListStoredQueriesRenderer [dir=back arrowtail=empty]
        XmlOutputRenderer -> DescribeStoredQueriesRenderer [dir=back arrowtail=empty]

        XmlOutputRenderer -> GML32Renderer [dir=back arrowtail=empty]
        CollectionOutputRenderer -> GML32Renderer [dir=back arrowtail=empty]
        CollectionOutputRenderer -> CSVRenderer [dir=back arrowtail=empty]
        CollectionOutputRenderer -> GeoJsonRenderer [dir=back arrowtail=empty]

        GML32Renderer -> DBGML32Renderer [dir=back arrowtail=empty]
        CSVRenderer -> DBCSVRenderer [dir=back arrowtail=empty]
        GeoJsonRenderer -> DBGeoJsonRenderer [dir=back arrowtail=empty]
    }

Various output formats have an DB-optimized version where the heavy rendering
of the EWKT, JSON or GML fragments is done by the database server.
Most output formats return a streaming response for performance.

Other WFS operations that also generate XML can implement a custom output renderer too.
The :class:`~gisserver.output.ListStoredQueriesRenderer` is a nice example for rendering custom XML responses.

The output rendering also translates the fully qualified XML names
into shortened QName format (e.g. ``{http://www.opengis.net/gml/3.2}Point`` becomes ``<gml:Point>``).

For fast development, the :class:`~gisserver.operations.base.WFSOperation`
may include the :class:`~gisserver.operations.base.XmlTemplateMixin` mixin
to render an XML template using Django templates. Currently, only ``GetCapabilities`` use that.

Applying the Projection
.......................

One special situation remains; the query also contains information about the "projection".
That is, how the retrieved data should be transformed before rendering.
Most notably, the ``<wfs:PropertyName>`` determines that only certain members should be rendered.

Practically, this information is also used by the :class:`~gisserver.parsers.wfs20.AdhocQuery`
so it can retrieve less data. For the collection rendering,
our internal :class:`~gisserver.projection.FeatureProjection` provides all information
to render the data, including which elements or which coordinate transformation to apply.

It also detects that relations can be prefetched, to avoid N-query calls for related models.
Just before rendering, the ``QuerySet`` is passed to
a :class:`~gisserver.output.CollectionOutputRenderer.decorate_queryset` function
of the output format.

Output Streaming
~~~~~~~~~~~~~~~~

The output rendering will generate a Django ``HttpResponse`` with the contents.
When the renderer class returns a generator, it will return a ``StreamingHttpResponse``
and hand that off to the WSGI server. The streaming rendering will help keep memory usage small.
Data is incrementally read from the database (in chunks),
and each chunk of rendered content (e.g. 40Kb) is written to the client.

Now the client can consume the data and present it!
