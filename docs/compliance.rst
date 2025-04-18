Standards Compliance
====================

Some facts about this project:

* All operations for the WFS Basic conformance class are implemented.
* The `CITE Test Suite <https://cite.opengeospatial.org/teamengine/>`_  only reveals a few bits left to implement.
* You should be able to view the WFS server `QGis <https://qgis.org/>`_.
* The unit tests validate the output against WFS 2.0 XSD schema.

Unimplemented Bits
------------------

Some remaining parts for the "WFS simple" conformance level are not implemented yet:

* KVP filters: ``aliases``.
* Remote resolving: ``resolveDepth``, ``resolveTimeout``.
* Some ``GetCapabilities`` features: ``acceptFormats`` and ``sections``.
* Temporal filtering.
* Tests on axis orientation.

Hopefully
---------

WFS-T support could be implemented on top of the existing POST parsing code.

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

* The ``<PropertyName>`` tag instead of ``<fes:ValueReference>``
* The ``<fes:Add>``, ``<fes:Sub>``, ``<fes:Mul>`` and ``<fes:Div>`` arithmetic operators, used by QGis.
* The ``FILTER=<Filter>...</Filter>`` parameter without an XML namespace declaration, typically seen in web-browser libraries.
* The ``MAXFEATURES`` parameter instead of ``COUNT``.
* The ``TYPENAME`` parameter instead of ``TYPENAMES`` (used by the CITE test suite!).
* Using ``A`` and ``D`` as sort direction in ``SORTBY`` / ``<fes:SortBy>`` instead of ``ASC`` and ``DESC``.

The FME (Feature Manipulation Engine) software sent ``OUTPUTFORMAT=application/gml+xml; version=3.2``
to all methods, including ``GetCapabilities`` and ``DescribeFeatureType``. These are also silently accepted.

For CITE test suite compliance, ``urn:ogc:def:query:OGC-WFS::GetFeatureById`` query returns an HTTP 404
for an invalid resource ID format, even though the WFS 2 specification states it should return
an ``InvalidParameterValue``. Likewise, the ``<ResourceId>`` query returns an empty list instead
of ``InvalidParameterValue`` for invalid resource ID formats.
This behavior can be disabled with the ``GISSERVER_WFS_STRICT_STANDARD`` setting.
