Standards Compliance
====================

Implemented Standards
---------------------

This project implements WFS 2.0 Simple, Basic and POST conformance classes.

* All operations for the WFS Basic conformance class are implemented.
* The `CITE Test Suite <https://cite.opengeospatial.org/teamengine/>`_ passes.
* You should be able to view the WFS server `QGis <https://qgis.org/>`_.
* The unit tests validate the output against WFS 2.0 XSD schema.

Unimplemented Classes
---------------------

The following additional conformance classes are not implemented:

* WFS-Transactional support (``<wfs:Transaction>``).
* Locking on updates: ``LockFeature``, ``GetFeatureWithLock``.
* Managing stored queries (``<wfs:CreateStoredQuery>`` / ``DropStoredQuery``).
* Temporal filtering (``<fes:After>``, ``<fes:Before>``, ``<fes:During>``, etc..).
* JOIN queries, which involves queries with multiple feature types for standard, spatial or temporal joins.
* Feature/resource versioning.
* SOAP requests.
* Transactional-safe pagination.

Any missing request types can be implemented on top of the existing POST parsing
code (see :doc:`overriding`).

Finally, these optional bits are not implemented, nor really needed:

* The ``GetCapabilities`` parameters ``acceptFormats`` and ``sections``.
* Remote resolving using ``resolveDepth`` and ``resolveTimeout``.

Hopefully
---------

While WMS and WMTS are not on the roadmap, they could be implemented based on
`Mapnik <https://github.com/mapnik>`_.
Other Python tiling logic such as
`TileCache <http://tilecache.org/>`_ and `TileStache <http://tilestache.org/>`_
could serve as inspiration too.

Low-Prio Items
--------------

Anything outside WFS-T could be implemented, but is very low on the todo-list:

* The methods for the WFS locking and inheritance conformance classes.
* SOAP requests.
* Other OGS protocols such as WCS
* Other output formats (shapefile, KML, GML 3.1) - but easy to add.

Some parts (such as output formats or missing WFS methods) can even
be implemented within your own project, by overriding the existing class attributes.

Compatibility with older WFS-clients
------------------------------------

Some popular WFS-clients still use aspects of the WFS 1.0 filter syntax in their queries.
To support these clients, the following logic is also implemented:

Filter Logic
............

* The ``<PropertyName>`` tag instead of ``<fes:ValueReference>``
* The ``<fes:Add>``, ``<fes:Sub>``, ``<fes:Mul>`` and ``<fes:Div>`` arithmetic operators, used by QGis.
* The ``FILTER=<Filter>...</Filter>`` parameter without an XML namespace declaration, typically seen in web-browser libraries.
* The ``MAXFEATURES`` parameter instead of ``COUNT``.
* The ``TYPENAME`` parameter instead of ``TYPENAMES`` (used by the CITE test suite!).
* Using ``A`` and ``D`` as sort direction in ``SORTBY`` / ``<fes:SortBy>`` instead of ``ASC`` and ``DESC``.

Coordinate Transformations
..........................

When an old syntax for coordinate transformation is used,
the output will be rendered in legacy longitude/latitude ordering.
It's mostly old JavaScript-based clients that use this.

This can be disabled with the :ref:`GISSERVER_FORCE_XY_EPSG_4326` settings.

When enabled, this applies to the ``SRSNAME=EPSG:4326`` parameter for projected output,
and the ``BBOX=...`` parameter / ``<fes:BBOX>`` filter for coordinate input.

The modern recommended notations ``urn:ogc:def:crs:EPSG::4326`` and ``http://www.opengis.net/def/crs/epsg/0/4326``,
used by modern GIS-software, will always render in the proper latitude/longitude ordering.
GeoJSON however, will always render in CRS84 longitude/latitude as the standard dictates.

Content Types
.............

The FME (Feature Manipulation Engine) software sent ``OUTPUTFORMAT=application/gml+xml; version=3.2``
to all methods, including ``GetCapabilities`` and ``DescribeFeatureType``. These are also silently accepted.

CITE Testing
............

For CITE test suite compliance, ``urn:ogc:def:query:OGC-WFS::GetFeatureById`` query returns an HTTP 404
for an invalid resource ID format, even though the WFS 2 specification states it should return
an ``InvalidParameterValue``. Likewise, the ``<ResourceId>`` query returns an empty list instead
of ``InvalidParameterValue`` for invalid resource ID formats.
This behavior can be disabled with the :ref:`GISSERVER_WFS_STRICT_STANDARD` setting.
