Welcome to django-gisserver's documentation!
============================================

Django speaking WFS 2.0 to expose geo data.

Features
--------

* WFS 2.0 Basic implementation.
* GML 3.2 output.
* Standard and spatial filtering (FES 2.0)
* GeoJSON and CSV export formats.
* Extensible view/operations.
* Uses GeoDjango queries for filtering.
* Streaming responses for large datasets.


.. toctree::
   :maxdepth: 1
   :caption: Usage Guide:

   quickstart
   feature_types
   settings
   troubleshooting

.. toctree::
   :maxdepth: 1
   :caption: Advanced Guide:

   overriding

.. toctree::
   :maxdepth: 1
   :caption: Background:

   user/filters
   compliance
   development


Why this code is shared
-----------------------

The "datapunt" team of the Municipality of Amsterdam develops software for the municipality.
Much of this software is then published as Open Source so that other municipalities,
organizations and citizens can use the software as a basis and inspiration to develop
similar software themselves. The Municipality of Amsterdam considers it important that
software developed with public money is also publicly available.

This package is initially developed by the City of Amsterdam, but the tools
and concepts created in this project can be used in any city.
