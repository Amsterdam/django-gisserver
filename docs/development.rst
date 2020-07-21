Development
============

When you follow the source of the `WFSView`, `WFSMethod` and `Parameter` classes,
you'll find that it's written with extensibility in mind. Extra parameters and operations
can easily be added there. You could even do that within your own projects and implementations.

A lot of the internal classes and object names are direct copies from the WFS spec.
By following these type definitions, a lot of the logic and code structure follows naturally.

The :file:`Makefile` gives you all you need to start working on the project.
Typing ``make`` gives an overview of all possible shortcut commands.

Internal logic
--------------

Features and Fields
~~~~~~~~~~~~~~~~~~~

Each :class:`~gisserver.features.FeatureField` is transformed into
an internal ``XsdElement`` object. The model field access happens
through ``XsdElement.get_value()``.
Note that the ``type`` can either reference either an ``XsdTypes`` or ``XsdComplexType``.

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
an internal ``XsdComplexType`` definition:

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

Data Retrieval
~~~~~~~~~~~~~~

When ``GetFeature`` or ``GetPropertyValue`` is called, several things happen:

* Request parsing.
* Query construction.
* Query execution.
* Output rendering.

The whole ``<fes:Filter>`` contents is translated an an internal "abstract syntax tree" (AST)
which closely resembles all class names that the FES standard defines.

Then, it's ``.get_query()`` method constructs the proper query object based on the request parameters.

The query class diagram looks like:

.. graphviz::

    digraph foo {
        QueryExpression [shape=box]
        AdhocQuery [shape=box]
        StoredQuery [shape=box]
        GetFeatureById [shape=box]
        custom [shape=box, label="..."]

        QueryExpression -> AdhocQuery [dir=back arrowtail=empty]
        QueryExpression -> StoredQuery [dir=back arrowtail=empty]
        StoredQuery -> GetFeatureById [dir=back arrowtail=empty]
        StoredQuery -> custom [dir=back arrowtail=empty]
    }

All regular requests such as ``?FILTER=...``, ``?BBOX=...``, ``?SORTBY=...``
and ``?RESOURCEID=...`` are handled by the ``AdhocQuery`` class.
A subclass of ``StoredQuery`` is used for ``?STOREDQUERY_ID=...`` requests.

The query is executed:

.. graphviz::

    digraph foo {

        QueryExpression [shape=box]
        CompiledQuery [shape=box]
        get_query [shape=none, label=".get_query()"]
        get_results [shape=none, label="query.get_results() / query.get_hits()", fontcolor="#1ba345"]
        get_type_names [shape=none, label=".get_type_names()", fontcolor="#1ba345"]
        get_queryset [shape=none, label=".get_queryset(feature_type)", fontcolor="#1ba345"]
        compile_query [shape=none, label=".compile_query()", fontcolor="#1ba345"]
        filter_queryset [shape=none, label="compiler.filter_queryset()"]

        get_query -> get_results [style=invis]
        get_query -> QueryExpression

        GetFeature -> get_query
        GetFeature -> get_results

        get_results -> get_type_names
        get_results -> get_queryset
        get_queryset -> compile_query
        get_queryset -> filter_queryset

        compile_query -> CompiledQuery
    }

The ``CompiledQuery`` collects all intermediate data needed
to translate the ``<fes:Filter>`` queries to a Django ORM call.
This object is passed though all nodes of the filter,
so each ``build...()`` function can add their lookups and annotations.

Output Rendering
~~~~~~~~~~~~~~~~

Each ``WFSMethod`` has a list of ``OutputFormat`` objects:

.. code-block:: python

    class GetFeature(BaseWFSGetDataMethod):
        output_formats = [
            OutputFormat("application/gml+xml", version="3.2", renderer_class=output.gml32_renderer),
            OutputFormat("text/xml", subtype="gml/3.2.1", renderer_class=output.gml32_renderer),
            OutputFormat("application/json", subtype="geojson", charset="utf-8", renderer_class=output.geojson_renderer),
            OutputFormat("text/csv", subtype="csv", charset="utf-8", renderer_class=output.csv_renderer),
            # OutputFormat("shapezip"),
            # OutputFormat("application/zip"),
        ]

The ``OutputFormat`` class may reference an ``renderer_class`` which points to an ``OutputRenderer`` object.

.. graphviz::

    digraph foo {
        node [shape=box]

        WFSMethod -> OutputFormat [label=".output_formats"]
        OutputFormat -> OutputRenderer [label=".renderer_class"]

        OutputRenderer -> CSVRenderer [dir=back arrowtail=empty]
        CSVRenderer -> DBCSVRenderer [dir=back arrowtail=empty]
        OutputRenderer -> GML32Renderer [dir=back arrowtail=empty]
        GML32Renderer -> DBGML32Renderer [dir=back arrowtail=empty]
        OutputRenderer -> GeoJsonRenderer [dir=back arrowtail=empty]
        GeoJsonRenderer -> DBGeoJsonRenderer [dir=back arrowtail=empty]
    }

Various output formats have an DB-optimized version where the heavy rendering
of the EWKT, JSON or GML fragments is done by the database server.
Most output formats return a streaming response for performance.

Alternatively, the ``WFSMethod`` may render an XML template using Django templates.


WFS Specification
-----------------

The WFS specification and examples be found at:

* https://www.opengeospatial.org/standards/ (all OGC standards)
* https://docs.opengeospatial.org/ (HTML versions)

Some deeplinks:

* https://www.opengeospatial.org/standards/common (OGC Web Service Common)
* https://www.opengeospatial.org/standards/wfs#downloads (OGC WFS)
* https://portal.opengeospatial.org/files/09-025r2 (WFS 2.0 spec)
* https://portal.opengeospatial.org/files/09-026r1 (OpenGIS Filter Encoding 2.0)
* https://portal.opengeospatial.org/files/07-036 (GML 3.2.1)

Other links:

* http://schemas.opengis.net/wfs/2.0/ (XSD and examples)
* https://mapserver.org/development/rfc/ms-rfc-105.html (more examples)

Accessing the CITE tests
------------------------

To perform CITE conformance testing against a server,
use `<https://cite.opengeospatial.org/teamengine/>`_.

At the bottom of the page, there is a "Register" button.
Create a new WFS 2.0 test session, and enter the URL, e.g.:

`http://example.org/v1/wfs/?VERSION=2.0.0&REQUEST=GetCapabilities`

Local testing can't be done with NGrok, as it exceeds the rate limiting.
Instead, consider opening a temporary port-forward at your router/modem.

