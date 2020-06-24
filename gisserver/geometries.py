"""Helper classes to handle geometry data types.

This includes the CRS parsing, coordinate transforms and bounding box object.
The bounding box can be calculated within Python, or read from a database result.
"""
import re
from dataclasses import dataclass, field

from django.contrib.gis.geos import GEOSGeometry, Polygon
from typing import Optional, Union

from django.contrib.gis.gdal import CoordTransform, SpatialReference
from functools import lru_cache

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


@lru_cache(maxsize=100)
def _get_spatial_reference(srid):
    """Construct an GDAL object reference"""
    # Using lru-cache to avoid repeated GDAL c-object construction
    return SpatialReference(srid, srs_type="epsg")


@lru_cache(maxsize=100)
def _get_coord_transform(
    source: Union[int, SpatialReference], target: Union[int, SpatialReference]
) -> CoordTransform:
    """Get an efficient coordinate transformation object.

    The CoordTransform should be used when performing the same
    coordinate transformation repeatedly on different geometries.

    NOTE that the cache could be busted when CRS objects are
    repeatedly created with a custom 'backend' object.
    """
    if isinstance(source, int):
        source = _get_spatial_reference(source)
    if isinstance(target, int):
        target = _get_spatial_reference(target)

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
    backend: Optional[SpatialReference] = None

    has_custom_backend: bool = field(init=False)

    def __post_init__(self):
        # Using __dict__ because of frozen=True
        self.__dict__["has_custom_backend"] = self.backend is not None

    @classmethod
    def from_string(
        cls, uri: Union[str, int], backend: Optional[SpatialReference] = None
    ) -> "CRS":
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
        """Instantiate this class using an numeric spatial reference ID

        This is logically identical to calling::

            CRS.from_string("urn:ogc:def:crs:EPSG:6.9:<SRID>")
        """
        return cls(
            domain="ogc",
            authority="EPSG",
            version="",
            crsid=str(srid),
            srid=int(srid),
            backend=backend,
        )

    @classmethod
    def _from_urn(cls, urn, backend=None):  # noqa: C901
        """Instantiate this class using an URN format."""
        urn_match = CRS_URN_REGEX.match(urn)
        if not urn_match:
            raise ValueError(
                f"Unknown CRS URN [{urn}] specified: {CRS_URN_REGEX.pattern}"
            )

        domain = urn_match.group("domain")
        authority = urn_match.group("authority").upper()

        if domain not in ("ogc", "opengis"):
            raise ValueError(f"CRS URI [{urn}] contains unknown domain [{domain}]")

        if authority == "EPSG":
            crsid = urn_match.group("id")
            try:
                srid = int(crsid)
            except ValueError:
                raise SyntaxError(
                    f"CRS URI [{urn}] should contain a numeric SRID value."
                ) from None
        elif authority == "OGC":
            crsid = urn_match.group("id").upper()
            if crsid != "CRS84":
                raise ValueError(f"OGC CRS URI from [{urn}] contains unknown id [{id}]")
            srid = 4326
        else:
            raise ValueError(
                f"CRS URI [{urn}] contains unknown authority [{authority}]"
            )

        return cls(
            domain=domain,
            authority=authority,
            version=urn_match.group(3),
            crsid=crsid,
            srid=srid,
            backend=backend,
        )

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
                    raise SyntaxError(
                        f"CRS URI [{uri}] should contain a numeric SRID value."
                    ) from None

                return cls(
                    domain="ogc",
                    authority="EPSG",
                    version="",
                    crsid=crsid,
                    srid=srid,
                    backend=backend,
                )

        raise ValueError(f"Unknown CRS URI [{uri}] specified")

    @property
    def legacy(self):
        """Return a legacy string in the format "EPSG:<srid>"""
        return f"EPSG:{self.srid:d}"

    @property
    def urn(self):
        """Return The OGC URN corresponding to this CRS. """
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
        return hash((self.authority, self.srid))

    def _as_gdal(self) -> SpatialReference:
        """Generate the GDAL Spatial Reference object"""
        if self.backend is None:
            # Avoid repeated construction
            self.__dict__["backend"] = _get_spatial_reference(self.srid)
        return self.backend

    def apply_to(self, geometry: GEOSGeometry, clone=False) -> Optional[GEOSGeometry]:
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
                return
        else:
            # Convert using GDAL / proj
            transform = _get_coord_transform(geometry.srid, self._as_gdal())
            return geometry.transform(transform, clone=clone)


WGS84 = CRS.from_srid(4326)  # aka EPSG:4326


@dataclass
class BoundingBox:
    """A bounding box that describes the extent of a map layer"""

    lower_lon: float
    lower_lat: float
    upper_lon: float
    upper_lat: float
    crs: Optional[CRS] = None

    @classmethod
    def from_string(cls, bbox):
        """Parse the bounding box from an input string.

        It can either be 4 coordinates, or 4 coordinates with a special reference system.
        """
        bbox = bbox.split(",")
        if not (4 <= len(bbox) <= 5):
            raise ValueError(
                f"Input does not contain bounding box, "
                f"expected 4 or 5 values, not {bbox}."
            )
        return cls(
            float(bbox[0]),
            float(bbox[1]),
            float(bbox[2]),
            float(bbox[3]),
            CRS.from_string(bbox[4]) if len(bbox) == 5 else None,
        )

    @classmethod
    def from_geometry(cls, geometry: GEOSGeometry, crs: Optional[CRS] = None):
        """Construct the bounding box for a geometry"""
        if crs is None:
            crs = CRS.from_srid(geometry.srid)
        elif geometry.srid != crs.srid:
            geometry = crs.apply_to(geometry, clone=True)

        return cls(*geometry.extent, crs=crs)

    @property
    def lower_corner(self):
        return [self.lower_lon, self.lower_lat]

    @property
    def upper_corner(self):
        return [self.upper_lon, self.upper_lat]

    def __repr__(self):
        return (
            "BoundingBox("
            f"{self.lower_lon}, {self.lower_lat}, {self.upper_lon}, {self.upper_lat}"
            ")"
        )

    def extend_to(
        self, lower_lon: float, lower_lat: float, upper_lon: float, upper_lat: float
    ):
        """Expand the bounding box in-place"""
        self.lower_lon = min(self.lower_lon, lower_lon)
        self.lower_lat = min(self.lower_lat, lower_lat)
        self.upper_lon = max(self.upper_lon, upper_lon)
        self.upper_lat = max(self.upper_lat, upper_lat)

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
                min(self.lower_lon, other.lower_lon),
                min(self.lower_lat, other.lower_lat),
                max(self.upper_lon, other.upper_lon),
                max(self.upper_lat, other.upper_lat),
            )
        else:
            return NotImplemented

    def as_polygon(self) -> Polygon:
        """Convert the value into a GEOS polygon."""
        polygon = Polygon.from_bbox(
            (self.lower_lon, self.lower_lat, self.upper_lon, self.upper_lat)
        )
        if self.crs is not None:
            polygon.srid = self.crs.srid
        return polygon
