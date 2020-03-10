"""GML support for the fes filtering.

Overview of GML 3.2 changes: https://mapserver.org/el/development/rfc/ms-rfc-105.html#rfc105
"""

from dataclasses import dataclass
from xml.etree.ElementTree import Element, tostring

from django.contrib.gis.geos import GEOSGeometry

from gisserver.parsers.base import tag_registry
from gisserver.parsers.utils import get_attribute
from gisserver.types import CRS

from .base import AbstractGeometry, TM_Object

GML21 = "http://www.opengis.net/gml"
GML32 = "http://www.opengis.net/gml/3.2"
_ANY_GML_NS = "{http://www.opengis.net/gml/"


def is_gml_element(element) -> bool:
    """Tell whether the element is an GML element."""
    return element.tag.startswith(_ANY_GML_NS)


@dataclass(repr=False)
@tag_registry.register("Polygon", GML21)
@tag_registry.register("LineString", GML32)
@tag_registry.register("LinearRing", GML32)
@tag_registry.register("MultiLineString", GML32)
@tag_registry.register("MultiPoint", GML32)
@tag_registry.register("MultiPolygon", GML32)
@tag_registry.register("MultiSurface", GML32)
@tag_registry.register("Point", GML32)
@tag_registry.register("Polygon", GML32)
@tag_registry.register("Envelope", GML32)
class GEOSGMLGeometry(AbstractGeometry):
    """Convert the incoming GML into a Django GEOSGeometry"""

    # Not implemented:
    # - Curve
    # - MultiCurve
    # - MultiGeometry
    # - Surface

    xml_ns = ...

    srs: CRS
    geos_data: GEOSGeometry

    @classmethod
    def from_xml(cls, element: Element):
        """Push the whole <gml:...> element into the GEOS parser.
        This avoids having to support the whole GEOS logic.

        GML is a complex beast with many different forms for the same thing:
        http://erouault.blogspot.com/2014/04/gml-madness.html
        """
        srs = CRS.from_string(get_attribute(element, "srsName"))

        # Push the whole <gml:...> element into the GEOS parser.
        # This avoids having to support the whole GEOS logic.
        geos_data = GEOSGeometry.from_gml(tostring(element))
        geos_data.srid = srs.srid
        return cls(srs=srs, geos_data=geos_data)

    def __repr__(self):
        # Better rendering for unit test debugging
        return f"GMLGEOSGeometry(srs={self.srs!r}, geos_data=GEOSGeometry({self.geos_data.wkt!r}))"

    @property
    def wkt(self) -> str:
        """Render the Geometry as well-known text"""
        return self.geos_data.wkt

    @property
    def json(self):
        return self.geos_data.json

    def build_rhs(self, fesquery):
        return self.geos_data


@tag_registry.register("After", GML32)
@tag_registry.register("Before", GML32)
@tag_registry.register("Begins", GML32)
@tag_registry.register("BegunBy", GML32)
@tag_registry.register("TContains", GML32)
@tag_registry.register("TEquals", GML32)
@tag_registry.register("TOverlaps", GML32)
@tag_registry.register("During", GML32)
@tag_registry.register("Meets", GML32)
@tag_registry.register("OverlappedBy", GML32)
@tag_registry.register("MetBy", GML32)
@tag_registry.register("EndedBy", GML32)
@tag_registry.register("AnyInteracts", GML32)
class TM_GeometricPrimitive(TM_Object):
    """Not implemented: the whole GML temporal logic"""

    xml_ns = GML32
