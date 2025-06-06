Troubleshooting
===============

While most errors should be self-explanatory,
this page lists anything that might be puzzling.


Latitude/longitude seem to be swapped
-------------------------------------

There is a lot to be said about `axis order confusion <https://wiki.osgeo.org/wiki/Axis_Order_Confusion>`_
and the [differences between software](https://macwright.com/lonlat/).

Basically, earlier geo-standards and software all assumed x/y-screen coordinates; implying longitude/latitude ordering.
This conflicts with various safety-critical environments such as nautical, aerial and ground navigation
that always worked in latitude/longitude. After a long debate, OGC and the WFS standard settled on using
the axis ordering by the authority of the CRS (Coordinate Reference System).

In practice this means:

* PostGIS and libgeos uses legacy x/y notations, so data is longitude/latitude.
* GeoJSON always always uses x/y notations for simplicity of web-based clients,
  so longitude/latitude by enforcing the CRS ``urn:ogc:def:crs:OGC::CRS84``.
* WFS 2.0, GDAL 3 and libproj follow the axis authority, so latitude/longitude.
* Various legacy and web-based software still assumes the legacy notation.

To handle a combination of legacy software, web-based clients, and modern systems
we implemented the `GeoServer Axis Ordering <https://docs.geoserver.org/stable/en/user/services/wfs/axis_order.html>`_ guidelines:

The following combinations of legacy formats trigger legacy handling:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Input
     - Axis Order Interpretation
   * - ``EPSG:4326`` + ``GISSERVER_FORCE_XY_EPSG_4326=True``
     - Classic format for WGS84, using: longitude/latitude.
   * - :samp:`http://www.opengis.net/gml/srs/epsg.xml#{code}` + ``GISSERVER_FORCE_XY_OLD_CRS=True``
     - legacy format, always: longitude/latitude.

These modern notations all follow the CRS authority:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Input
     - Description
   * - :samp:`EPSG:{code}`
     - All EPSG notations, except EPSG:4326 above.
   * - :samp:`urn:ogc:def:crs:EPSG:{code}`
     - Modern URN format, follows CRS authority.
   * - :samp:`http://www.opengis.net/def/crs/epsg/0/{code}`
     - Modern URI format, follows CRS authority.

It's worth noting that ``urn:ogc:def:crs:EPSG::4326`` and ``urn:ogc:def:crs:OGC::CRS84``
are both defined as SRID 4326. However, CRS84 is defined as longitude/latitude axis
and EPSG notation has a latitude/longitude axis.

Since PostGIS uses GEOS, the raw data should be stored as longitude/latitude format.
When the modern ``urn:ogc:def:crs:EPSG::4326`` projection is requested, the coordinates
will be swapped during rendering.


Operation on mixed SRID geometries
----------------------------------

The error "Operation on mixed SRID geometries" often indicates
that the database table uses a different SRID
then the ``GeometryField(srid=..)`` configuration in Django assumes.


Only numeric values of degree units are allowed on geographic DWithin queries
-----------------------------------------------------------------------------

The ``DWithin`` / ``Beyond`` can only use unit-based distances when the model
field defines a projected system (e.g. ``PointField(srid=...)``).
Otherwise, only the units of the geometry field are supported (e.g. degrees for WGS84).
If it's possible to work around this limitation, a pull request is welcome.


ProgrammingError / InternalError database exceptions
----------------------------------------------------

When an ``ProgrammingError`` or ``InternalError`` happens, this likely means the database
table schema doesn't match with the Django model. As WFS queries allow clients to
construct complex queries against a table, any discrepancies between the Django model
and database table are bound to show up.

For example, if your database table uses an ``INTEGER`` or ``CHAR(1)`` type,
but declares a ``BooleanField`` in Django this will cause errors.
Django can only construct queries in reliably when the database schema
matches the model definition.

Make sure your Django model migrations have been applied,
or that any imported database tables matches the model definition.


InvalidCursorName cursor "_django_curs_..." does not exist
----------------------------------------------------------

This error happens when the database connection passes through a connection pooler
(e.g. PgBouncer). One workaround is wrapping the view inside ``@transaction.atomic``,
or disabling server-side cursors entirely by adding ``DISABLE_SERVER_SIDE_CURSORS = True`` to the settings.

For details,
see: https://docs.djangoproject.com/en/stable/ref/databases/#transaction-pooling-server-side-cursors


Sentry SDK truncates the exceptions for filters
-----------------------------------------------

The Sentry SDK truncates log messages after 512 characters.
This typically truncates the contents of the ``FILTER`` parameter,
as it's XML notation is quite verbose.
Add the following to your settings file to see the complete message:

.. code-block:: python

    import sentry_sdk.utils

    sentry_sdk.utils.MAX_STRING_LENGTH = 2048  # for WFS FILTER exceptions
