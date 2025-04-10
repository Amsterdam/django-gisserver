Overriding Server Logic
=======================

There are a few places where the server logic can be extended:

There are a few places that allow to customize the WFS logic:

View Layer
----------

The following methods of the :class:`~gisserver.views.WFSView` can be overwritten:

* :meth:`~gisserver.views.WFSView.get_feature_types` to dynamically generate all exposed features.
* :meth:`~gisserver.views.WFSView.get_service_description` to dynamically generate the description.
* :meth:`~gisserver.views.WFSView.dispatch` to implement basic auth.

Feature Layer
-------------

Overriding :class:`~gisserver.features.FeatureType` allows to change how particular features and fields are exposed.
It can also override the internal XML Schema Definition (XSD) that all output and query filters read.

This can also adjust the

* Overriding :meth:`~gisserver.features.FeatureType.check_permissions` allows to perform a permission check before the feature can be read (e.g. a login role check).
* Overriding :meth:`~gisserver.features.FeatureType.get_queryset` allows to define the queryset per request.
* Overriding :attr:`~gisserver.features.FeatureType.xsd_type` constructs the internal XSD definition of this feature.
* Overriding :attr:`~gisserver.features.FeatureType.xsd_type_class` defines which class constructs the XSD.

The :func:`~gisserver.features.field` function returns a :class:`~gisserver.features.FeatureField`.
Instances of this class can be passed directly to the ``FeatureType(fields=...)`` parameter,
and override these attributes:

* :attr:`~gisserver.features.FeatureField.xsd_element` constructs the internal XSD that filters and output formats use.
* :attr:`~gisserver.features.FeatureField.xsd_element_class` defines which class defines the attribute.

XSD Layer
---------

The feature fields generate an internal XML Schema Definition (XSD) that defines how
properties are read, and where the underlying ORM field/relation can be found.
These types can be overwritten for custom behavior, and then be returned by
custom :class:`~gisserver.features.FeatureType` and :class:`~gisserver.features.FeatureField` objects.

* :class:`~gisserver.types.XsdComplexType` defines a complete class with elements and attributes.
* :class:`~gisserver.types.XsdElement` defines a property that becomes a normal element.
* :class:`~gisserver.types.XsdAttribute` defines the attributes (only ``gml:id`` is currently rendered).

The elements and attributes have the following fields:

* :attr:`~gisserver.types.XsdNode.orm_path` - returns where to find the ORM relation.
* :attr:`~gisserver.types.XsdNode.orm_field` - returns the first part of the ORM relation.
* :attr:`~gisserver.types.XsdNode.orm_relation` - returns the ORM relation as path and final field name.
* :meth:`~gisserver.types.XsdNode.get_value` - how to read the attribute value.
* :meth:`~gisserver.types.XsdNode.format_value` - format raw-retrieved values from the database (e.g ``.values()`` query).
* :meth:`~gisserver.types.XsdNode.to_python` - how to cast input data.
* :meth:`~gisserver.types.XsdNode.validate_comparison` - checks a field supports a certain data type.
* :meth:`~gisserver.types.XsdNode.build_lhs_part` - how to generate the ORM left-hand-side.
* :meth:`~gisserver.types.XsdNode.build_rhs_part` - how to generate the ORM right-hand-side.

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
