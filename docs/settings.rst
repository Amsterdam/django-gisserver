Configuration Settings
======================

The following configuration settings can be used to tweak server behavior.

The defaults are:

.. code-block:: python

    import math

    # Flags
    GISSERVER_CAPABILITIES_BOUNDING_BOX = True
    GISSERVER_USE_DB_RENDERING = True
    GISSERVER_SUPPORTED_CRS_ONLY = True
    GISSERVER_COUNT_NUMBER_MATCHED = 1

    # Output rendering
    GISSERVER_EXTRA_OUTPUT_FORMATS = {}
    GISSERVER_GET_FEATURE_OUTPUT_FORMATS = {}

    # Max page size
    GISSERVER_DEFAULT_MAX_PAGE_SIZE = 5000
    GISSERVER_GEOJSON_MAX_PAGE_SIZE = math.inf
    GISSERVER_CSV_MAX_PAGE_SIZE = math.inf

    # For debugging
    GISSERVER_WRAP_FILTER_DB_ERRORS = True
    GISSERVER_WFS_STRICT_STANDARD = False


GISSERVER_CAPABILITIES_BOUNDING_BOX
-----------------------------------

By default, the ``GetCapabilities`` response includes the bounding box of each feature.
Since this is an expensive operation for large datasets, this can be disabled entirely.

If the project has the ``CACHES`` setting configured, the result will be briefly stored in a cache.


GISSERVER_USE_DB_RENDERING
--------------------------

By default, complex GML, GeoJSON and EWKT fragments are rendered by the database.
This gives a better performance compared to GeoDjango, which needs to
perform C-API calls indo GDAL for every coordinate of a geometry.

However, if you're not using PostgreSQL+PostGIS, you may want to disable this optimization.


GISSERVER_SUPPORTED_CRS_ONLY
----------------------------

By default, clients may only request features in one of the supported coordinate reference systems
that the ``FeatureType`` has listed. Often databases (such as PostGIS) and the GDAL backend support
a lot more out of the box. By disabling this setting, all system-wide supported CRS values can be
used in the ``?SRSNAME=...`` parameter.

For performance reasons, the last 100 GDAL ``CoordTransform`` objects are stored in-memory.
Allowing clients to change the output format so freely may cause some performance loss there.


GISSERVER_COUNT_NUMBER_MATCHED
------------------------------

By default, the whole page size is calculated. However, performing a ``COUNT`` is expensive in SQL.
By disabling this, clients just simply need to fetch more pages.
Possible values:

* 0 = No counting.
* 1 = Apply counting for all pages (the default).
* 2 = Apply counting only for the first page.

In the WFS output, ``number_matched="unknown"`` will be found when paging is disabled.


GISSERVER\_..._OUTPUT_FORMATS
-----------------------------

The ``GISSERVER_*_OUTPUT_FORMATS`` settings make it easier to declare additional output formats.
An example would be:

.. code-block:: python

    GISSERVER_EXTRA_OUTPUT_FORMATS = {
        "content-type": {
            "renderer_class": "dotted.path.to.CustomRenderer"
            "subtype": "type-alias",
            "title": "HTML title",
        },
    }

See :doc:`extensions` for a discussion on the required code.


GISSERVER\_..._MAX_PAGE_SIZE
----------------------------

The ``GISSERVER_*_MAX_PAGE_SIZE`` settings allow to limit what the maximum requestable page size is.
For GeoJSON and CSV, this is set to an infinite number which disables
paging unless the ``?COUNT=...`` request parameter is used.

.. note::
    QGis often requests 1000 features per request, regardless of the maximum page size.
    Custom ``OutputRenderer`` subclasses may also override this setting.


GISSERVER_WFS_STRICT_STANDARD
-----------------------------

By default, the server is configured to pass CITE conformance tests.
Strictly speaking, the WFS server should return an exception when an invalid ``RESOURCEID`` format is offered
that doens't follow the "typename.identifier" notation.


GISSERVER_WRAP_FILTER_DB_ERRORS
-------------------------------

By default, filter errors are nicely wrapped inside a WFS exception.
This can be disabled for debugging purposes.
