"""GML support for the fes filtering.

Overview of GML 3.2 changes: https://mapserver.org/el/development/rfc/ms-rfc-105.html#rfc105
"""

from dataclasses import dataclass
from xml.etree.ElementTree import tostring

from django.contrib.gis.gdal import AxisOrder
from django.contrib.gis.geos import GEOSGeometry, Polygon

from gisserver.crs import CRS
from gisserver.exceptions import ExternalParsingError
from gisserver.parsers.ast import tag_registry
from gisserver.parsers.query import CompiledQuery
from gisserver.parsers.xml import NSElement, xmlns

from .base import AbstractGeometry, AbstractTimePrimitive

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
        CRS.tag_geometry(polygon, axis_order=AxisOrder.AUTHORITY)
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

        # Using the WFS 2 format (urn:ogc:def:crs:EPSG::4326"), coordinates should be latitude/longitude.
        # However, when providing legacy formats like srsName="EPSG:4326",
        # input is assumed to be in legacy longitude/latitude axis ordering too.
        # This reflects what GeoServer does: https://docs.geoserver.org/main/en/user/services/wfs/axis_order.html
        if not srs.force_xy:
            CRS.tag_geometry(geos_data, axis_order=AxisOrder.AUTHORITY)
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

        # Make sure the data is suitable for processing by the ORM.
        # The database needs the geometry in traditional (x/y) ordering.
        if self.srs.is_north_east_order:
            return self.srs.apply_to(self.geos_data, clone=True, axis_order=AxisOrder.TRADITIONAL)
        else:
            return self.geos_data


@tag_registry.register("TimeInstant", hidden=True)
@tag_registry.register("TimePeriod", hidden=True)
class AbstractTimeGeometricPrimitive(AbstractTimePrimitive):
    """Not implemented: the whole GML temporal logic.

    Examples for GML time elements include::

      <gml:TimeInstant gml:id="TI1">
         <gml:timePosition>2005-05-19T09:28:40Z</gml:timePosition>
      </gml:TimeInstant>

    and::

      <gml:TimePeriod gml:id="TP1">
         <gml:begin>
            <gml:TimeInstant gml:id="TI1">
               <gml:timePosition>2005-05-17T00:00:00Z</gml:timePosition>
            </gml:TimeInstant>
         </gml:begin>
         <gml:end>
            <gml:TimeInstant gml:id="TI2">
               <gml:timePosition>2005-05-23T00:00:00Z</gml:timePosition>
            </gml:TimeInstant>
         </gml:end>
      </gml:TimePeriod>
    """

    xml_ns = xmlns.gml32


@tag_registry.register("TimeNode", hidden=True)
@tag_registry.register("TimeEdge", hidden=True)
class AbstractTimeTopologyPrimitiveType(AbstractTimePrimitive):
    """Not implemented: GML temporal logic for TimeNode/TimeEdge."""

    xml_ns = xmlns.gml32
