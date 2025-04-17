Development
============

.. contents:: :local:

The :file:`Makefile` gives you all you need to start working on the project.
Typing ``make`` gives an overview of all possible shortcut commands.


Running tests
-------------

The :file:`Makefile` has all options. Just typing ``make`` gives a list of all commands.

Using ``make test``, and ``make retest`` should run the pytest suite.

A special ``make docker-test`` runs the tests as they would run within Travis-CI.
This helps to debug any differences between coordinate transformations due to
different PROJ.4 versions being installed.

Accessing the CITE tests
------------------------

To perform CITE conformance testing against a server,
use `<https://cite.opengeospatial.org/teamengine/>`_.

* At the bottom of the page, there is a **Create an account** button.
* Create a new WFS 2.0 test session
* At the next page, enter the URL to the ``GetCapabilities`` document, e.g.:

``http://example.org/v1/wfs/?VERSION=2.0.0&REQUEST=GetCapabilities``


Local testing
~~~~~~~~~~~~~
Local testing can't be done with NGrok, as it exceeds the rate limiting.
Instead, consider opening a temporary port-forward at your router/modem and
using the online test suite.
Alternatively, you can build a local test suite runner from source.

In either case, you need to create a local server that serves at least one
model with some geofield on it. One can copy over the code from the test/
test_gisserver folder into a new django project, and removing what you don't
need. If you built new functionality that may affect the outcome of the tests,
ensure that this is also available in this app.

NB:
- It is easiest if you disable CSRF here, as the POST requests would otherwise
encounter 403's.
- Ensure you use a postgres DB rather than the default SQLite.
- Run your migrations
- This app is also suitable to test everything in QGIS/ArcGIS.

The local test suite runner can be built from this repo:

``https://github.com/opengeospatial/ets-wfs20``

You need java and maven (mvn) for this. For the rest you can follow the
instructions in the readme of said repo, where you put the url of your
local server in the `test-run-props.xml` file.

In the future we may build a docker image for the test suite and can
perform them on CI. Right now, some edge-cases are still not implemented by
choice, so these tests would fail.

Understanding the Code
----------------------

Please see :doc:`architecture`.

.. _wfs-spec:

WFS 2.0 Specification
---------------------

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
* https://www.mediamaps.ch/ogc/schemas-xsdoc/sld/1.2/ (browsable XSD)

Coordinate systems, and axis orientation:

* https://macwright.com/lonlat/ (the inconsistency of lat/lon or lon/lat)
* https://macwright.com/2015/03/23/geojson-second-bite.html (More than you ever wanted to know about GeoJSON)
* https://mapserver.org/ogc/wms_server.html#coordinate-systems-and-axis-orientation (mapserver WMS part)
* https://mapserver.org/ogc/wfs_server.html#axis-orientation-in-wfs-1-1-and-2-0 (mapserver WFS part)
* https://docs.geoserver.org/stable/en/user/services/wms/basics.html#axis-ordering (geoserver WMS part)
* https://docs.geoserver.org/stable/en/user/services/wfs/axis_order.html (geoserver WFS part)
