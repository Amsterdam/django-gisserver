Extending the Server
====================

There are a few places where the server logic can be extended,
to include custom output formats, filtering functions and stored queries.

Custom Output Formats
---------------------

Each WFS operation supports various output formats.
These can be extended, for example:

.. code-block:: python

    from gisserver.output.base import CollectionOutputRenderer


    class ShapeZipRenderer(CollectionOutputRenderer):
        content_type = "application/zip"
        content_disposition = 'attachment; filename="{typenames} {page} {date}.zip"'
        max_page_size = None  # allow to override the default, can also be pass math.inf.

        def render_stream(self):
            for sub_collection in self.collection.results:
                projection = sub_collection.projection

                for instance in sub_collection:
                    yield ...

The ``render_stream()`` method may return the whole content as
a single ``str``/``bytes``/``StringIO``/``BytesIO`` block,
or provide chunks of ``str``/``byte`` objects using ``yield``.

The "projection" tells which properties are selected for rendering,
and which SRS to use for the output.

These need to be registered in the settings:

.. code-block:: python

    GISSERVER_EXTRA_OUTPUT_FORMATS = {
        "content-type": {
            "renderer_class": "dotted.path.to.CustomRenderer"
            "title": "HTML title",
        },
    }

The output format is chosen when either the *content-type*
or ``subtype`` is used in the ``OUTPUTFORMAT`` parameter.

Allowed fields are:

* ``renderer_class`` (required): dotted path, or reference to a :class:`~gisserver.output.CollectionOutputRenderer` subclass.
* ``subtype``: optional alias for the content-type.
* ``max_page_size``: optionally max page size, ``math.inf`` gives infinite paging.
* ``title``: optional title for the HTML page.
* any other field is used as content-type directive (e.g. ``charset`` or ``version``).

Methods that can be defined include:

* :meth:`~gisserver.output.OutputRenderer.get_headers` to add extra HTTP headers
* :meth:`~gisserver.output.OutputRenderer.render_exception` tells how to render an exception mid-stream.
* :meth:`~gisserver.output.CollectionOutputRenderer.decorate_queryset` allows to optimize the QuerySet for the output format.
* :meth:`~gisserver.output.CollectionOutputRenderer.get_prefetch_queryset` allows to optimize the QuerySet for prefetched relations.

For XML-based rendering, by including :class:`~gisserver.output.XmlOutputRenderer`:

* :attr:`~gisserver.output.XmlOutputRenderer.xml_namespaces` defines extra XML namespaces,
  which are combined with :attr:`~gisserver.views.WFSView.xml_namespace_aliases`.
* The methods :meth:`~gisserver.output.XmlOutputRenderer.render_xmlns_attributes`,
  :meth:`~gisserver.output.XmlOutputRenderer.to_qname` and :meth:`~gisserver.output.XmlOutputRenderer.feature_to_qname`
  help with creating the proper abbreviated XML tag notations.

Custom Filter Functions
-----------------------

.. warning::
   While the machinery to hook new functions is in place, this part is still in development.

As part of the WFS Filter Encoding, a client can execute a function against a server.
These are executed with ``?REQUEST=GetFeature&FILTER...``

An expression such as: **table_count == Add("previous_table_count", 100)**
would be encoded in the following way using the Filter Encoding Specification (FES):

.. code-block:: xml

        <fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">
            <fes:PropertyIsEqualTo>
                <fes:ValueReference>table_count</fes:ValueReference>
                <fes:Function name="Add">
                    <fes:ValueReference>previous_table_count</fes:ValueReference>
                    <fes:Literal>100</fes:Literal>
                </fes:Function>
            </fes:PropertyIsEqualTo>
        </fes:Filter>

These FES functions can be defined in the project,
by generating a corresponding database function.

Use :attr:`gisserver.extensions.functions.function_registry` to register new functions:

.. code-block:: python

    from django.db.models import functions
    from gisserver.extensions.functions import function_registry
    from gisserver.types import XsdTypes


    # Either link an exising Django ORM function:

    function_registry.register(
        "atan",
        functions.ATan,
        arguments={"value": XsdTypes.double},
        returns=XsdTypes.double,
    )


    # Or link a parsing logic that generates an ORM function/object:

    @function_registry.register(
        name="Add",
        arguments=dict(value1=XsdTypes.double, value2=XsdTypes.double),
        returns=XsdTypes.double,
    )
    def fes_add(value1, value2):
        return F(value1) + value2

Each FES function should return a Django ORM ``Func`` or ``Combinable`` object.


Custom Stored Procedures
------------------------

.. warning::
   While the machinery to add new stored procedures is in place, this part is still in development.

Aside from filters, a WFS server can also expose "stored procedures".
These are executed with ``?REQUEST=GetFeature&STOREDQUERY_ID=...``
By default, only ``GetFeatureById`` is built-in.

These stored procedures can be defined like this:

.. code-block:: python

    from datetime import date
    from gisserver.extensions.queries import StoredQueryImplementation, stored_query_registry
    from gisserver.parsers.query import compiledQuery
    from gisserver.types import XsdTypes


    @stored_query_registry.register(
        # Provide the metadata.
        id="GetRecentChanges",
        title="Get recent changes",
        abstract="All recent changes from the Django admin log",
        parameters={"startFrom": XsdTypes.date},
    )
    class GetRecentChanges(StoredQueryImplementation):

        def __init__(self, startFrom: date):
            self.start_from = startFrom

        def get_type_names():
            return ["{http://example.org/gisserver}LogEntry"]

        def build_query(compiler: CompiledQuery) -> Q:
            return Q(action_time__gte=self.start_from)


For a simple implementation, the following methods need to be overwritten:

* :meth:`~gisserver.extensions.queries.StoredQueryImplementation.get_type_names` defines which feature types this query applies to.
* :meth:`~gisserver.extensions.queries.StoredQueryImplementation.build_query` defines how to filter the queryset.
