"""The base classes for GML.

See "Table D.2" in the GML 3.2.1 spec, showing how the UML names
map to the GML implementations. These names are referenced by the FES spec.
"""
from gisserver.parsers.base import BaseNode


class GM_Object(BaseNode):
    """Abstract base classes for all GML objects, regardless of their version.

    <gml:AbstractGeometry> implements the ISO 19107 GM_Object.
    """


class GM_Envelope(BaseNode):
    """Abstract base classes for all GML objects, regardless of their version.

    <gml:Envelope> implements ISO 19107 GM_Envelope (see D.2.3.4 and ISO 19107:2003, 6.4.3).
    """


class TM_Object(BaseNode):
    """Abstract base classes for temporal GML objects, regardless of their version.

    See ISO 19108 TM_Object (see D.2.5.2 and ISO 19108:2002, 5.2.2)
    """


# Instead of polluting the MRO with unneeded levels,
# create aliases:
AbstractGeometry = GM_Object
Envelope = GM_Envelope
