Development
============

.. contents:: :local:

The :file:`Makefile` gives you all you need to start working on the project.
Typing ``make`` gives an overview of all possible shortcut commands.


Running tests
-------------

The :file:`Makefile` has all options. Just typing ``make`` gives a list of all commands.

Using ``make test``, and ``make retest`` should run the pytest suite.

A special ``make docker-test`` runs the tests against a recent Ubuntu version.
This helps to debug any differences between coordinate transformations due to
different PROJ.4 versions being installed.

Accessing the CITE tests
------------------------

To perform CITE conformance testing against an online server,
use `<https://cite.opengeospatial.org/teamengine/>`_.

* At the bottom of the page, there is a **Create an account** button.
* Create a new WFS 2.0 test session
* At the next page, enter the URL to the ``GetCapabilities`` document, e.g.:

``http://example.org/v1/wfs/?VERSION=2.0.0&REQUEST=GetCapabilities``

This can't be used for local testing with NGrok, as it exceeds the rate limiting.
You'll have to run the code on a public URL, or use a temporary port-forward at your router/modem.

Local testing
~~~~~~~~~~~~~

Local testing is possible against the example app.
Make sure it uses a PostgreSQL+Postgis database, and uses::

    export GISSERVER_WFS_STRICT_STANDARD=false

Start either::

    ./example/manage.py runserver 0.0.0.0:8000

or::

    docker compose up

Start the docker version of the CITE test suite::

    make ogctest  # runs: docker run --rm -it -p 8081:8080 ogccite/ets-wfs20

* Open: http://localhost:8081/teamengine/
* Login using username: ``ogctest``  password: ``ogctest``
* Click on `View sessions <http://localhost:8081/teamengine/viewSessions.jsp>`_
* Click on `Create a new session <http://localhost:8081/teamengine/createSession.jsp>`_
* Enter the fields:

  * Organization: **OGC**
  * Specification: **Web Feature Service (WFS) - 2.0 [ 1.43 ]**
  * Description: can stay empty.

* In the next screen, for *Location of WFS capabilities document:*, enter the URL:
  ``http://host.docker.internal:8000/wfs/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities``

In the future we may use the docker image for testing on CI.
Right now, some edge-cases are still not implemented yet, so these tests would fail.

Building the Cite Test Suite
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The local test suite runner can be built from: https://github.com/opengeospatial/ets-wfs20.

You need java and maven (mvn) for this. For the rest you can follow the
instructions in the readme of said repo, where you put the url of your
local server in the `test-run-props.xml` file which contains::

    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
    <properties version="1.0">
        <comment>Test run arguments for ets-wfs20</comment>
        <entry key="wfs">http://localhost:8000/wfs/?SERVICE=WFS&amp;REQUEST=GetCapabilities</entry>
    </properties>


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
* https://wiki.osgeo.org/wiki/Axis_Order_Confusion
* https://mapserver.org/ogc/wms_server.html#coordinate-systems-and-axis-orientation (mapserver WMS part)
* https://mapserver.org/ogc/wfs_server.html#axis-orientation-in-wfs-1-1-and-2-0 (mapserver WFS part)
* https://docs.geoserver.org/stable/en/user/services/wms/basics.html#axis-ordering (geoserver WMS part)
* https://docs.geoserver.org/stable/en/user/services/wfs/axis_order.html (geoserver WFS part)
