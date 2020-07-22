Standards Compliance
====================

Some facts about this project:

* Nearly all operations for the WFS Basic conformance class are implemented.
* The `CITE Test Suite <https://cite.opengeospatial.org/teamengine/>`_  only reveals a few bits left to implement.
* You should be able to view the WFS server `QGis <https://qgis.org/>`_.
* The unit tests validate the output against WFS 2.0 XSD schema.

Unimplemented Bits
------------------

Some remaining parts for the "WFS simple" conformance level are not implemented yet:

* KVP filters: `propertyName`, `aliases`.
* Remote resolving: `resolveDepth`, `resolveTimeout`.
* Multiple queries in a single GET call.
* Some `GetCapabilities` features: `acceptFormats` and `sections`.
* Temporal filtering (high on todo)

Planned
-------

* WFS-T (Transactional) support, which also needs HTTP POST requests.

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
