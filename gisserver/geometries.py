"""Helper classes to handle geometry data types.

This includes the CRS parsing, coordinate transforms and bounding box object.
The bounding box can be calculated within Python, or read from a database result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache

from django.contrib.gis.gdal import CoordTransform, SpatialReference
from django.contrib.gis.geos import GEOSGeometry, Polygon

from gisserver.exceptions import ExternalParsingError, ExternalValueError

CRS_URN_REGEX = re.compile(
    r"^urn:(?P<domain>[a-z]+)"
    r":def:crs:(?P<authority>[a-z]+)"
    r":(?P<version>[0-9]+\.[0-9]+(\.[0-9]+)?)?"
    r":(?P<id>[0-9]+|crs84)"
    r"$",
    re.IGNORECASE,
)

__all__ = [
    "CRS",
    "WGS84",
    "BoundingBox",
]


@lru_cache(maxsize=200)
def _get_spatial_reference(srs_input, srs_type="user", axis_order=None):
    """Construct an GDAL object reference"""
    # Using lru-cache to avoid repeated GDAL c-object construction
    return SpatialReference(srs_input, srs_type=srs_type, axis_order=axis_order)


@lru_cache(maxsize=100)
def _get_coord_transform(
    source: int | SpatialReference, target: int | SpatialReference
) -> CoordTransform:
    """Get an efficient coordinate transformation object.

    The CoordTransform should be used when performing the same
    coordinate transformation repeatedly on different geometries.

    NOTE that the cache could be busted when CRS objects are
    repeatedly created with a custom 'backend' object.
    """
    if isinstance(source, int):
        source = _get_spatial_reference(source, srs_type="epsg")
    if isinstance(target, int):
        target = _get_spatial_reference(target, srs_type="epsg")

    return CoordTransform(source, target)


@dataclass(frozen=True)
class CRS:
    """
    Represents a CRS (Coordinate Reference System), which preferably follows the URN format
    as specified by `the OGC consortium <http://www.opengeospatial.org/ogcUrnPolicy>`_.
    """

    # CRS logic, based upon https://github.com/wglas85/django-wfs/blob/master/wfs/helpers.py
    # Copyright (c) 2006 Wolfgang Glas - Apache 2.0 licensed
    # Ported to Python 3.6 style.

    #: Either "ogc" or "opengis", whereas "ogc" is highly recommended.
    domain: str

    #: Either "OGC" or "EPSG".
    authority: str

    #: The version of the authorities' SRS registry, which is empty or
    #: contains two or three numeric components separated by dots like "6.9" or "6.11.9".
    #: For WFS 2.0 this is typically empty.
    version: str

    #: A string representation of the coordinate system reference ID.
    #: For OGC, only "CRS84" is supported as crsid. For EPSG, this is the formatted CRSID.
    crsid: str

    #: The integer representing the numeric spatial reference ID as
    #: used by the EPSG and GIS database backends.
    srid: int

    #: GDAL SpatialReference with PROJ.4 / WKT content to describe the exact transformation.
    backend: SpatialReference | None = None

    #: Original input
    origin: str = field(init=False, default=None)

    has_custom_backend: bool = field(init=False)

    def __post_init__(self):
        # Using __dict__ because of frozen=True
        self.__dict__["has_custom_backend"] = self.backend is not None

    @classmethod
    def from_string(cls, uri: str | int, backend: SpatialReference | None = None) -> CRS:
        """
        Parse an CRS (Coordinate Reference System) URI, which preferably follows the URN format
        as specified by `the OGC consortium <http://www.opengeospatial.org/ogcUrnPolicy>`_
        and construct a new CRS instance.

        The value can be 3 things:

        * A URI in OGC URN format.
        * A legacy CRS URI ("epsg:<SRID>", or "http://www.opengis.net/...").
        * A numeric SRID (which calls `from_srid()`)
        """
        if isinstance(uri, int) or uri.isdigit():
            return cls.from_srid(int(uri), backend=backend)
        elif uri.startswith("urn:"):
            return cls._from_urn(uri, backend=backend)
        else:
            return cls._from_legacy(uri, backend=backend)

    @classmethod
    def from_srid(cls, srid: int, backend=None):
        """Instantiate this class using a numeric spatial reference ID

        This is logically identical to calling::

            CRS.from_string("urn:ogc:def:crs:EPSG:6.9:<SRID>")
        """
        crs = cls(
            domain="ogc",
            authority="EPSG",
            version="",
            crsid=str(srid),
            srid=int(srid),
            backend=backend,
        )
        crs.__dict__["origin"] = srid
        return crs

    @classmethod
    def _from_urn(cls, urn, backend=None):  # noqa: C901
        """Instantiate this class using a URN format."""
        urn_match = CRS_URN_REGEX.match(urn)
        if not urn_match:
            raise ExternalValueError(f"Unknown CRS URN [{urn}] specified: {CRS_URN_REGEX.pattern}")

        domain = urn_match.group("domain")
        authority = urn_match.group("authority").upper()

        if domain not in ("ogc", "opengis"):
            raise ExternalValueError(f"CRS URI [{urn}] contains unknown domain [{domain}]")

        if authority == "EPSG":
            crsid = urn_match.group("id")
            try:
                srid = int(crsid)
            except ValueError:
                raise ExternalValueError(
                    f"CRS URI [{urn}] should contain a numeric SRID value."
                ) from None
        elif authority == "OGC":
            crsid = urn_match.group("id").upper()
            if crsid != "CRS84":
                raise ExternalValueError(f"OGC CRS URI from [{urn}] contains unknown id [{id}]")
            srid = 4326
        else:
            raise ExternalValueError(f"CRS URI [{urn}] contains unknown authority [{authority}]")

        crs = cls(
            domain=domain,
            authority=authority,
            version=urn_match.group(3),
            crsid=crsid,
            srid=srid,
            backend=backend,
        )
        crs.__dict__["origin"] = urn
        return crs

    @classmethod
    def _from_legacy(cls, uri, backend=None):
        """Instantiate this class from a legacy URL"""
        luri = uri.lower()
        for head in (
            "epsg:",
            "http://www.opengis.net/def/crs/epsg/0/",
            "http://www.opengis.net/gml/srs/epsg.xml#",
        ):
            if luri.startswith(head):
                crsid = luri[len(head) :]
                try:
                    srid = int(crsid)
                except ValueError:
                    raise ExternalValueError(
                        f"CRS URI [{uri}] should contain a numeric SRID value."
                    ) from None

                crs = cls(
                    domain="ogc",
                    authority="EPSG",
                    version="",
                    crsid=crsid,
                    srid=srid,
                    backend=backend,
                )
                crs.__dict__["origin"] = uri
                return crs

        raise ExternalValueError(f"Unknown CRS URI [{uri}] specified")

    @property
    def legacy(self):
        """Return a legacy string in the format "EPSG:<srid>"""
        return f"EPSG:{self.srid:d}"

    @property
    def urn(self):
        """Return The OGC URN corresponding to this CRS."""
        return f"urn:{self.domain}:def:crs:{self.authority}:{self.version or ''}:{self.crsid}"

    def __str__(self):
        return self.urn

    def __eq__(self, other):
        if isinstance(other, CRS):
            # CRS84 is NOT equivalent to EPSG:4326.
            # EPSG:4326 specifies coordinates in lat/long order and CRS:84 in long/lat order.
            return self.authority == other.authority and self.srid == other.srid
        else:
            return NotImplemented

    def __hash__(self):
        """Used to match objects in a set."""
        return hash((self.authority, self.srid))

    def _as_gdal(self) -> SpatialReference:
        """Generate the GDAL Spatial Reference object"""
        if self.backend is None:
            # Avoid repeated construction, reuse the object from cache if possible.
            # Note that the original data is used, as it also defines axis orientation.
            if self.origin:
                self.__dict__["backend"] = _get_spatial_reference(self.origin)
            else:
                self.__dict__["backend"] = _get_spatial_reference(self.srid, srs_type="epsg")
        return self.backend

    def apply_to(self, geometry: GEOSGeometry, clone=False) -> GEOSGeometry | None:
        """Transform the geometry using this coordinate reference.

        This method caches the used CoordTransform object

        Every transformation within this package happens through this method,
        giving full control over coordinate transformations.
        """
        if self.srid == geometry.srid:
            # Avoid changes if spatial reference system is identical.
            if clone:
                return geometry.clone()
            else:
                return None
        else:
            # Convert using GDAL / proj
            transform = _get_coord_transform(geometry.srid, self._as_gdal())
            return geometry.transform(transform, clone=clone)


WGS84 = CRS.from_srid(4326)  # aka EPSG:4326


@dataclass
class BoundingBox:
    """A bounding box (or "envelope") that describes the extent of a map layer"""

    south: Decimal  # longitude
    west: Decimal  # latitude
    north: Decimal  # longitude
    east: Decimal  # latitude
    crs: CRS | None = None

    @classmethod
    def from_string(cls, bbox):
        """Parse the bounding box from an input string.

        It can either be 4 coordinates, or 4 coordinates with a special reference system.
        """
        bbox = bbox.split(",")
        if not (4 <= len(bbox) <= 5):
            raise ExternalParsingError(
                f"Input does not contain bounding box, expected 4 or 5 values, not {bbox}."
            )
        return cls(
            Decimal(bbox[0]),
            Decimal(bbox[1]),
            Decimal(bbox[2]),
            Decimal(bbox[3]),
            CRS.from_string(bbox[4]) if len(bbox) == 5 else None,
        )

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

    def as_polygon(self) -> Polygon:
        """Convert the value into a GEOS polygon."""
        polygon = Polygon.from_bbox((self.south, self.west, self.north, self.east))
        if self.crs is not None:
            polygon.srid = self.crs.srid
        return polygon
