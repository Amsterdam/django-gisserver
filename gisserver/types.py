"""Internal data types

This exposes helper classes to parse GEO data types.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union

from django.contrib.gis.geos import GEOSGeometry, Point, Polygon

CRS_URN_REGEX = re.compile(
    r"^urn:(?P<domain>[a-z]+)"
    r":def:crs:(?P<authority>[a-z]+)"
    r":(?P<version>[0-9]+\.[0-9]+(\.[0-9]+)?)?"
    r":(?P<id>[0-9]+|crs84)"
    r"$",
    re.IGNORECASE,
)

__all__ = [
    "BoundingBox",
    "CRS",
    "WGS84",
]


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
        if geometry.crs.srid != self.crs.srid:
            geometry = geometry.transform(self.crs.srid, clone=True)

        if isinstance(geometry, Point):
            self.extend_to(geometry.x, geometry.y, geometry.x, geometry.y)
        else:
            raise NotImplementedError(f"Processing {geometry} is not implemented")

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

    @classmethod
    def from_string(cls, uri: Union[str, int]):
        """
        Parse an CRS (Coordinate Reference System) URI, which preferably follows the URN format
        as specified by `the OGC consortium <http://www.opengeospatial.org/ogcUrnPolicy>`_
        and construct a new CRS instance.

        The value can be 3 things:

        * A URI in OGC URN format.
        * A legacy CRS URI ("epsg:<SRID>", or "http://www.opengis.net/...").
        * A numeric SRID (equivalent to "urn:ogc:def:crs:EPSG:6.9:<SRID>")
        """
        if isinstance(uri, int):
            return cls._from_srid(uri)
        elif uri.startswith("urn:"):
            return cls._from_urn(uri)
        else:
            return cls._from_legacy(uri)

    @classmethod
    def _from_srid(cls, srid: int):
        """Instantiate this class using an numeric spatial reference ID"""
        return cls(
            domain="ogc", authority="EPSG", version="", crsid=str(srid), srid=int(srid),
        )

    @classmethod
    def _from_urn(cls, urn):  # noqa: C901
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
        )

    @classmethod
    def _from_legacy(cls, uri):
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
                    domain="ogc", authority="EPSG", version="", crsid=crsid, srid=srid,
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


WGS84 = CRS.from_string(4326)  # aka EPSG:4326
