"""Helper classes to handle geometry data types.

The bounding box can be calculated within Python, or read from a database result.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.contrib.gis.geos import GEOSGeometry

from gisserver.crs import CRS, CRS84, WEB_MERCATOR, WGS84  # noqa: F401 (keep old exports)

__all__ = [
    "BoundingBox",
]


@dataclass
class BoundingBox:
    """A bounding box (or "envelope") that describes the extent of a map layer"""

    south: Decimal  # longitude
    west: Decimal  # latitude
    north: Decimal  # longitude
    east: Decimal  # latitude
    crs: CRS | None = None

    @classmethod
    def from_geometry(cls, geometry: GEOSGeometry, crs: CRS | None = None):
        """Construct the bounding box for a geometry"""
        if crs is None:
            crs = CRS.from_srid(geometry.srid)
        elif geometry.srid != crs.srid:
            geometry = crs.apply_to(geometry, clone=True)

        return cls(*geometry.extent, crs=crs)

    @property
    def lower_corner(self):
        return [self.south, self.west]

    @property
    def upper_corner(self):
        return [self.north, self.east]

    def __repr__(self):
        return f"BoundingBox({self.south}, {self.west}, {self.north}, {self.east})"

    def extend_to(self, lower_lon: float, lower_lat: float, upper_lon: float, upper_lat: float):
        """Expand the bounding box in-place"""
        self.south = min(self.south, lower_lon)
        self.west = min(self.west, lower_lat)
        self.north = max(self.north, upper_lon)
        self.east = max(self.east, upper_lat)

    def extend_to_geometry(self, geometry: GEOSGeometry):
        """Extend this bounding box with the coordinates of a given geometry."""
        if self.crs is not None and geometry.srid != self.crs.srid:
            geometry = self.crs.apply_to(geometry, clone=True)

        self.extend_to(*geometry.extent)

    def __add__(self, other):
        """Combine both extents into a larger box."""
        if isinstance(other, BoundingBox):
            if other.crs != self.crs:
                raise ValueError(
                    "Can't combine instances with different spatial reference systems"
                )
            return BoundingBox(
                min(self.south, other.south),
                min(self.west, other.west),
                max(self.north, other.north),
                max(self.east, other.east),
            )
        else:
            return NotImplemented
