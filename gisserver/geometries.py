"""Helper classes to handle geometry data types.

The bounding box can be calculated within Python, or read from a database result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from django.contrib.gis.geos import GEOSGeometry

from gisserver.crs import CRS, CRS84, WEB_MERCATOR, WGS84  # noqa: F401 (keep old exports)

#: The CRS for the ``<ows:WGS84BoundingBox>`` element:
WGS84_BOUNDING_BOX_CRS = CRS.from_string("urn:ogc:def:crs:OGC:2:84")

__all__ = [
    "BoundingBox",
    "WGS84BoundingBox",
]


@dataclass
class BoundingBox:
    """A bounding box.
    Due to the overlap between 2 types, this element is used for 2 cases:

    * The ``<ows:WGS84BoundingBox>`` element for ``GetCapabilities``.
    * The ``<gml:Envelope>`` inside an ``<gml:boundedBy>``  single feature.

    While both classes have no common base class (and exist in different schema's),
    their properties are identical.

    The X/Y coordinates can be either latitude or longitude, depending on the CRS.

    Note this isn't using the GDAL/OGR "Envelope" object, as that doesn't expose the CRS,
    and requires constant copies to merge geometries.
    """

    min_x: float
    min_y: float
    max_x: float
    max_y: float
    crs: CRS | None = None

    @classmethod
    def from_geometries(cls, geometries: list[GEOSGeometry], crs: CRS) -> BoundingBox | None:
        """Calculate the extent of a collection of geometries."""
        if not geometries:
            return None
        elif len(geometries) == 1:
            # Common case: feature has a single geometry
            ogr_geometry = geometries[0].ogr
            crs.apply_to(ogr_geometry, clone=False)
            return cls(*ogr_geometry.extent, crs=crs)
        else:
            # Feature has multiple geometries.
            # Start with an obviously invalid bbox,
            # which corrects at the first extend_to_geometry call.
            result = cls(math.inf, math.inf, -math.inf, -math.inf, crs=crs)

            for geometry in geometries:
                ogr_geometry = geometry.ogr
                crs.apply_to(ogr_geometry, clone=False)
                result.extend_to(*ogr_geometry.extent)

            return result

    @property
    def lower_corner(self):
        return [self.min_x, self.min_y]

    @property
    def upper_corner(self):
        return [self.max_x, self.max_y]

    def extend_to(self, min_x: float, min_y: float, max_x: float, max_y: float):
        """Expand the bounding box in-place"""
        self.min_x = min(self.min_x, min_x)
        self.min_y = min(self.min_y, min_y)
        self.max_x = max(self.max_x, max_x)
        self.max_y = max(self.max_y, max_y)

    def __add__(self, other):
        """Combine both extents into a larger box."""
        if isinstance(other, BoundingBox):
            if other.crs != self.crs:
                raise ValueError(
                    "Can't combine instances with different spatial reference systems"
                )
            return self.__class__(
                min(self.min_x, other.min_x),
                min(self.min_y, other.min_y),
                max(self.max_x, other.max_x),
                max(self.max_y, other.max_y),
                crs=self.crs,
            )
        else:
            return NotImplemented


class WGS84BoundingBox(BoundingBox):
    """The ``<ows:WGS84BoundingBox>`` element for the ``GetCapabilities`` element.

    This always has coordinates are always in longitude/latitude axis ordering,
    the CRS is fixed to ``urn:ogc:def:crs:OGC:2:84``.
    """

    def __init__(self, min_x: float, min_y: float, max_x: float, max_y: float):
        super().__init__(min_x, min_y, max_x, max_y, crs=WGS84_BOUNDING_BOX_CRS)
