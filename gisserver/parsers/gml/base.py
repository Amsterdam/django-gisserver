"""The base classes for GML.

See "Table D.2" in the GML 3.2.1 spec, showing how the UML names
map to the GML implementations. These names are referenced by the FES spec.
"""

from __future__ import annotations

from gisserver.parsers.ast import AstNode
from gisserver.parsers.query import CompiledQuery

__all__ = (
    "GM_Object",
    "GM_Envelope",
    "TM_Object",
    "AbstractTimeObject",
    "AbstractTimePrimitive",
    "Envelope",
    "AbstractGeometry",
)


class GM_Object(AstNode):
    """Abstract base classes for all GML objects, regardless of their version."""

    def build_rhs(self, compiler: CompiledQuery):
        """Required function to implement.
        This allows using the value to be used in a binary operator.
        """
        raise NotImplementedError()


class GM_Envelope(AstNode):
    """Abstract base classes for the GML envelope, regardless of their version."""


class TM_Object(AstNode):
    """Abstract base classes for temporal GML objects, regardless of their version.

    See ISO 19108 TM_Object (see D.2.5.2 and ISO 19108:2002, 5.2.2)
    """


# Instead of polluting the MRO with unneeded base classes, create aliases:

#: The ``<gml:AbstractGeometry>`` definition implements the ISO 19107 GM_Object.
AbstractGeometry = GM_Object

#: The ``<gml:Envelope>`` implements ISO 19107 GM_Envelope (see D.2.3.4 and ISO 19107:2003, 6.4.3).
Envelope = GM_Envelope

# See https://www.mediamaps.ch/ogc/schemas-xsdoc/sld/1.1.0/temporal_xsd.html

#: The base class for all time objects
AbstractTimeObject = TM_Object

#: The base classes for time primitives.
AbstractTimePrimitive = AbstractTimeObject
