"""GML support for the fes filtering.

Overview of GML 3.2 changes: https://mapserver.org/el/development/rfc/ms-rfc-105.html#rfc105
"""

from dataclasses import dataclass
from xml.etree.ElementTree import tostring

from django.contrib.gis.geos import GEOSGeometry, Polygon

from gisserver.exceptions import ExternalParsingError
from gisserver.geometries import CRS
from gisserver.parsers.ast import tag_registry
from gisserver.parsers.query import CompiledQuery
from gisserver.parsers.xml import NSElement, xmlns

from .base import AbstractGeometry, TM_Object

_ANY_GML_NS = "{http://www.opengis.net/gml/"


def is_gml_element(element) -> bool:
    """Tell whether the element is an GML element."""
    return element.tag.startswith(_ANY_GML_NS)


@dataclass(repr=False)
@tag_registry.register("Polygon", xmlns.gml21)
@tag_registry.register("LineString", xmlns.gml32)
@tag_registry.register("LinearRing", xmlns.gml32)
@tag_registry.register("MultiLineString", xmlns.gml32)
@tag_registry.register("MultiPoint", xmlns.gml32)
@tag_registry.register("MultiPolygon", xmlns.gml32)
@tag_registry.register("MultiSurface", xmlns.gml32)
@tag_registry.register("Point", xmlns.gml32)
@tag_registry.register("Polygon", xmlns.gml32)
@tag_registry.register("Envelope", xmlns.gml32)
class GEOSGMLGeometry(AbstractGeometry):
    """Convert the incoming GML into a Django GEOSGeometry.
    This tag parses all ``<gml:...>`` geometry elements within the query.
    """

    # Not implemented:
    # - Curve
    # - MultiCurve
    # - MultiGeometry
    # - Surface

    srs: CRS
    geos_data: GEOSGeometry

    @classmethod
    def from_bbox(cls, bbox_value: str):
        """Parse the bounding box from an input string.

        It can either be 4 coordinates, or 4 coordinates with a special reference system.
        """
        bbox = bbox_value.split(",")
        if not (4 <= len(bbox) <= 5):
            raise ExternalParsingError(
                f"Input does not contain bounding box, expected 4 or 5 values, not {bbox}."
            )

        polygon = Polygon.from_bbox(
            (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        )
        if len(bbox) == 5:
            crs = CRS.from_string(bbox[4])
            polygon.srid = crs.srid
        else:
            crs = None  # will be resolved

        # Wrap in an element that the filter can use.
        return cls(srs=crs, geos_data=polygon)

    @classmethod
    def from_xml(cls, element: NSElement):
        """Push the whole <gml:...> element into the GEOS parser.
        This avoids having to support the whole GEOS logic.

        GML is a complex beast with many different forms for the same thing:
        http://erouault.blogspot.com/2014/04/gml-madness.html
        """
        srs = CRS.from_string(element.get_str_attribute("srsName"))

        # Push the whole <gml:...> element into the GEOS parser.
        # This avoids having to support the whole GEOS logic.
        geos_data = GEOSGeometry.from_gml(tostring(element))
        geos_data.srid = srs.srid
        return cls(srs=srs, geos_data=geos_data)

    def __repr__(self):
        # Better rendering for unit test debugging
        return f"{self.__class__.__name__}(srs={self.srs!r}, geos_data=GEOSGeometry({self.geos_data.wkt!r}))"

    @property
    def wkt(self) -> str:
        """Render the Geometry as well-known text"""
        return self.geos_data.wkt

    @property
    def json(self):
        return self.geos_data.json

    def build_rhs(self, compiler: CompiledQuery):
        # Perform final validation during the construction of the query.
        if self.srs is None:
            # When the feature type is known, apply its default CRS.
            # This is not possible in XML parsing, but may happen for BBOX parsing.
            self.srs = compiler.feature_types[0].crs
            self.geos_data.srid = self.srs.srid  # assign default CRS to geometry
        elif compiler.feature_types:  # for unit tests
            self.srs = compiler.feature_types[0].resolve_crs(self.srs, locator="bbox")

        return self.geos_data


@tag_registry.register("After")
@tag_registry.register("Before")
@tag_registry.register("Begins")
@tag_registry.register("BegunBy")
@tag_registry.register("TContains")
@tag_registry.register("TEquals")
@tag_registry.register("TOverlaps")
@tag_registry.register("During")
@tag_registry.register("Meets")
@tag_registry.register("OverlappedBy")
@tag_registry.register("MetBy")
@tag_registry.register("EndedBy")
@tag_registry.register("AnyInteracts")
class TM_GeometricPrimitive(TM_Object):
    """Not implemented: the whole GML temporal logic"""

    xml_ns = xmlns.gml32
