Overriding Server Logic
=======================

There are a few places where the server logic can be overwritten:

There are a few places that allow to customize the WFS logic:

View Layer
----------

The following methods of the :class:`~gisserver.views.WFSView` can be overwritten:

* :meth:`~gisserver.views.WFSView.get_feature_types` to dynamically generate all exposed features.
* :meth:`~gisserver.views.OWSView.get_service_description` to dynamically generate the description.
* :attr:`~gisserver.views.OWSView.xml_namespace_aliases` can define aliases for namespaces. (default is ``{"app": self.xml_namespace}``).
* :meth:`~gisserver.views.OWSView.dispatch` to implement basic auth.
* :meth:`~gisserver.views.WFSView.check_permissions` to check for permissions

The permission checks can access the `self.request.user` object in Django,
and inspect the fully parsed WFS request in `self.request.ows_request`.

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
* :meth:`~gisserver.types.XsdNode.format_raw_value` - format raw-retrieved values from the database (e.g ``.values()`` query).
* :meth:`~gisserver.types.XsdNode.to_python` - how to cast input data.
* :meth:`~gisserver.types.XsdNode.validate_comparison` - checks a field supports a certain data type.
* :meth:`~gisserver.types.XsdNode.build_lhs_part` - how to generate the ORM left-hand-side.
* :meth:`~gisserver.types.XsdNode.build_rhs_part` - how to generate the ORM right-hand-side.

Request Parsing
---------------

The classes in :mod:`gisserver.parsers.wfs20` translate the XML POST request into an internal
representation of the request. Each class closely mirrors the definitions in the WFS 2.0 specification.
The GET request parsing (KVP format) is a special case of these classes.

New parser classes may be added for operations that are not implemented yet (such as WFS-T or creating stored queries).
Subsequently, a :class:`~gisserver.operations.base.WFSOperation` needs to be implemented that handles this request.
That operation needs to be registered in :class:`~gisserver.views.WFSView`'s ``accept_operations`` attribute.
The :class:`~gisserver.operations.base.WFSOperation` may also define a ``parser_class`` to
override which parser handles the request.
