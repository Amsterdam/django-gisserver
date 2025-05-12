gisserver.geometries module
===========================

.. automodule:: gisserver.geometries
   :show-inheritance:

Default Coordinate Reference Systems
------------------------------------

.. autoattribute:: gisserver.geometries.WGS84
   :no-value:

   Worldwide GPS, latitude/longitude (y/x), see https://epsg.io/4326.
   Generated output as ``urn:ogc:def:crs:EPSG::4326``.

.. autoattribute:: gisserver.geometries.CRS84
   :no-value:

   The default for GeoJSON output. This is like WGS84 but with axis as longitude/latitude (x/y).
   Generates output as ``urn:ogc:def:crs:OGC::CRS84``.

.. autoattribute:: gisserver.geometries.WEB_MERCATOR
   :no-value:

   The WGS84/pseudo-mercator aka Spherical Mercator projection, see https://epsg.io/3857.
   This is used by Google Maps, Bing Maps, OpenStreetMap, etc...
   Generates output as ``urn:ogc:def:crs:EPSG::3857``.


The ``CRS`` Class
-----------------

.. autoclass:: gisserver.geometries.CRS
   :members:

The ``BoundingBox`` Class
-------------------------

.. autoclass:: gisserver.geometries.BoundingBox
   :members:
