API Documentation
=================

.. seealso::

    See the :ref:`architecture` page for a high-level overview of all classes.

.. automodule:: gisserver
    :members:
    :undoc-members:
    :show-inheritance:

.. toctree::
   :maxdepth: 1
   :caption: Core Definitions

   gisserver.crs
   gisserver.features
   gisserver.types

.. toctree::
   :maxdepth: 1
   :caption: Request Handling

   gisserver.exceptions
   gisserver.operations.base
   gisserver.operations.wfs20
   gisserver.views

.. toctree::
   :maxdepth: 1
   :caption: Parsing

   gisserver.parsers
   gisserver.parsers.ast
   gisserver.parsers.fes20
   gisserver.parsers.gml
   gisserver.parsers.ows
   gisserver.parsers.xml
   gisserver.parsers.query
   gisserver.parsers.values

.. toctree::
   :maxdepth: 1
   :caption: Output Rendering

   gisserver.geometries
   gisserver.output
   gisserver.output.utils
   gisserver.projection
   gisserver.templatetags.gisserver_tags

.. toctree::
   :maxdepth: 1
   :caption: Extensibility

   gisserver.extensions
   gisserver.extensions.functions
   gisserver.extensions.queries
