gisserver.output package
========================

.. automodule:: gisserver.output

Base classes
---------------

.. autoclass:: gisserver.output.OutputRenderer
   :members:

.. autoclass:: gisserver.output.CollectionOutputRenderer
   :members:

.. autoclass:: gisserver.output.XmlOutputRenderer
   :members:

.. autofunction:: gisserver.output.to_qname

See also:

.. toctree::
   :maxdepth: 1

   gisserver.output.utils

Collections
-----------

.. autoclass:: gisserver.output.FeatureCollection
   :members:

.. autoclass:: gisserver.output.SimpleFeatureCollection
   :members:


Implementations
---------------

Output Formats
..............

.. autoclass:: gisserver.output.GML32Renderer
.. autoclass:: gisserver.output.GML32ValueRenderer
.. autoclass:: gisserver.output.CSVRenderer
.. autoclass:: gisserver.output.GeoJsonRenderer

Database-Optimized Output Formats
.................................

.. autoclass:: gisserver.output.DBGML32Renderer
.. autoclass:: gisserver.output.DBGML32ValueRenderer
.. autoclass:: gisserver.output.DBGeoJsonRenderer
.. autoclass:: gisserver.output.DBCSVRenderer

Other XML Responses
...................

.. autoclass:: gisserver.output.ListStoredQueriesRenderer
.. autoclass:: gisserver.output.DescribeStoredQueriesRenderer
.. autoclass:: gisserver.output.XmlSchemaRenderer
