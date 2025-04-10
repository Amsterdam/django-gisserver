"""All parser logic to process incoming XML data.

This handles all tags, including:

* ``<wfs:...>``
* ``<fes:...>``
* ``<gml:...>``

Internally, the XML string is translated into an Abstract Syntax Tree (AST).
These objects contain to logic to process each bit of the XML tree.
The GET request parameters are translated into that same tree structure,
to have a uniform processing of the request.
"""
