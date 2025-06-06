"""Helper classes for Coordinate Reference System translations.

This includes the CRS parsing, coordinate transforms and axis orientation.
"""

from __future__ import annotations

import logging
import re
import typing
from dataclasses import dataclass, field
from functools import cached_property, lru_cache

import pyproj
from django.contrib.gis.gdal import AxisOrder, CoordTransform, OGRGeometry, SpatialReference
from django.contrib.gis.geos import GEOSGeometry

from gisserver import conf
from gisserver.exceptions import ExternalValueError

CRS_URN_REGEX = re.compile(
    r"^urn:(?P<domain>[a-z]+)"
    r":def:crs:(?P<authority>[a-z]+)"
    r":(?P<version>[0-9]+(\.[0-9]+(\.[0-9]+)?)?)?"
    r":(?P<id>[0-9]+|crs84)"
    r"$",
    re.IGNORECASE,
)

AnyGeometry = typing.TypeVar("AnyGeometry", GEOSGeometry, OGRGeometry)

__all__ = [
    "CRS",
    "CRS84",
    "WEB_MERCATOR",
    "WGS84",
]

# Caches to avoid reinitializing WGS84 each time.
_COMMON_CRS_BY_STR = {}
_COMMON_CRS_BY_SRID = {}


logger = logging.getLogger(__name__)


@lru_cache(maxsize=200)  # Using lru-cache to avoid repeated GDAL c-object construction
def _get_spatial_reference(srs_input: str | int, srs_type, axis_order):
    """Construct an GDAL object reference"""
    logger.debug(
        "Constructed GDAL SpatialReference(%r, srs_type=%r, axis_order=%s)",
        srs_input,
        srs_type,
        axis_order,
    )
    return SpatialReference(srs_input, srs_type=srs_type, axis_order=axis_order)


@lru_cache(maxsize=100)
def _get_coord_transform(source: SpatialReference, target: SpatialReference) -> CoordTransform:
    """Get an efficient coordinate transformation object.

    The CoordTransform should be used when performing the same
    coordinate transformation repeatedly on different geometries.

    Using a CoordinateTransform also allows setting the AxisOrder setting
    on both ends. When calling ``GEOSGeometry.transform()``, Django will
    create an internal CoordTransform object internally without setting AxisOrder,
    implicitly setting its source SpatialReference to be 'AxisOrder.TRADITIONAL'.
    """
    return CoordTransform(source, target)


_get_proj_crs_from_string = lru_cache(maxsize=10)(pyproj.CRS.from_string)
_get_proj_crs_from_authority = lru_cache(maxsize=10)(pyproj.CRS.from_authority)


@dataclass(frozen=True, eq=False)
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
    backends: tuple[SpatialReference, SpatialReference] = (None, None)

    #: Original input
    origin: str = field(init=False, default=None)

    #: Tell whether the input format used the legacy notation.
    force_xy: bool = False

    @classmethod
    def from_string(cls, uri: str | int) -> CRS:
        """
        Parse an CRS (Coordinate Reference System) URI, which preferably follows the URN format
        as specified by `the OGC consortium <http://www.opengeospatial.org/ogcUrnPolicy>`_
        and construct a new CRS instance.

        The value can be 3 things:

        * A URI in OGC URN format.
        * A legacy CRS URI ("epsg:<SRID>", or "http://www.opengis.net/...").
        * A numeric SRID (which calls :meth:`from_srid()`)
        """
        if known_crs := _COMMON_CRS_BY_STR.get(uri):
            return known_crs  # Avoid object re-creation

        if isinstance(uri, int) or uri.isdigit():
            return cls.from_srid(int(uri))
        elif uri.startswith("urn:"):
            return cls._from_urn(uri)
        else:
            return cls._from_prefix(uri)

    @classmethod
    def from_srid(cls, srid: int):
        """Instantiate this class using a numeric spatial reference ID

        This is logically identical to calling::

            CRS.from_string("urn:ogc:def:crs:EPSG::<SRID>")
        """
        if common_crs := _COMMON_CRS_BY_SRID.get(srid):
            return common_crs  # Avoid object re-creation

        return cls(
            domain="ogc",
            authority="EPSG",
            version="",
            crsid=str(srid),
            srid=int(srid),
        )

    @classmethod
    def _from_urn(cls, urn):  # noqa: C901
        """Instantiate this class using a URN format.
        This format is defined in https://portal.ogc.org/files/?artifact_id=30575.
        """
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
            # urn:ogc:def:crs:OGC::CRS84 has x/y ordering (longitude/latitude)
            crsid = urn_match.group("id").upper()
            if crsid not in ("CRS84", "84"):
                raise ExternalValueError(f"OGC CRS URI from [{urn}] contains unknown id [{id}]")
            srid = 4326
        else:
            raise ExternalValueError(f"CRS URI [{urn}] contains unknown authority [{authority}]")

        crs = cls(
            domain=domain,
            authority=authority,
            version=urn_match.group(3) or "",
            crsid=crsid,
            srid=srid,
        )
        crs.__dict__["origin"] = urn
        return crs

    @classmethod
    def _from_prefix(cls, uri):
        """Instantiate this class from a non-URI notation.

        The modern URL format (:samp:`http://www.opengis.net/def/crs/epsg/0/{xxxx}`)
        is defined in https://portal.ogc.org/files/?artifact_id=46361.

        Older notations like :samp:`EPSG:{xxxx}` or legacy XML URLs like
        and :samp`:http://www.opengis.net/gml/srs/epsg.xml#{xxxx}` are also supported.
        """
        # Make sure origin uses the expected upper/lowercasing.
        origin = uri.lower() if "://" in uri else uri.upper()
        for prefix, force_xy in (
            (
                "EPSG:",
                (conf.GISSERVER_FORCE_XY_EPSG_4326 and origin == "EPSG:4326"),
            ),
            (
                "http://www.opengis.net/gml/srs/epsg.xml#",
                conf.GISSERVER_FORCE_XY_OLD_CRS,
            ),
            ("http://www.opengis.net/def/crs/epsg/0/", False),
        ):
            if origin.startswith(prefix):
                crsid = origin[len(prefix) :]
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
                    force_xy=force_xy,
                )
                crs.__dict__["origin"] = origin
                return crs

        raise ExternalValueError(f"Unknown CRS URI [{uri}] specified")

    @property
    def legacy(self):
        """Return a legacy string in the format :samp:`http://www.opengis.net/gml/srs/epsg.xml#{srid}`."""
        # This mirrors what GeoSever does, as this notation always has an axis ordering defined.
        # Notations like EPSG:xxxx notation don't have such consistent usage.
        return f"http://www.opengis.net/gml/srs/epsg.xml#{self.srid:d}"

    @cached_property
    def urn(self):
        """Return The OGC URN corresponding to this CRS."""
        return f"urn:{self.domain}:def:crs:{self.authority}:{self.version or ''}:{self.crsid}"

    @property
    def is_north_east_order(self) -> bool:
        """Tell whether the axis is in north/east ordering."""
        return self.axis_direction == ["north", "east"]

    @cached_property
    def axis_direction(self) -> list[str]:
        """Tell what the axis ordering of this coordinate system is.

        For example, WGS84 will return ``['north', 'east']``.

        While computer systems typically use X,Y, other systems may use northing/easting.
        Historically, latitude was easier to measure and given first.
        In physics, using 'radial, polar, azimuthal' is again a different perspective.
        See: https://wiki.osgeo.org/wiki/Axis_Order_Confusion for a good summary.
        """
        proj_crs = self._as_proj()
        return [axis.direction for axis in proj_crs.axis_info]

    def __str__(self):
        return self.legacy if self.force_xy else self.urn

    def __eq__(self, other):
        if isinstance(other, CRS):
            return self.matches(other, compare_legacy=True)
        else:
            return NotImplemented

    def matches(self, other, compare_legacy=True) -> bool:
        """Tell whether this CRS is identical to another one."""
        return (
            # "urn:ogc:def:crs:EPSG::4326" != "urn:ogc:def:crs:OGC::CRS84"
            # even through they both share the same srid.
            self.srid == other.srid
            and self.authority == other.authority
            and (
                # Also, legacy notations like EPSG:4326 are treated differently,
                # unless this is configured to not make a difference.
                not compare_legacy
                or self.force_xy == other.force_xy
            )
        )

    def __hash__(self):
        """Used to match objects in a set."""
        return hash((self.authority, self.srid))

    def _as_gdal(self, axis_order: AxisOrder) -> SpatialReference:
        """Generate the GDAL Spatial Reference object."""
        if self.backends[axis_order] is None:
            backends = list(self.backends)
            if self.origin and "://" not in self.origin:  # avoid downloads and OGR errors
                # Passing the origin helps to detect CRS84 strings
                backends[axis_order] = _get_spatial_reference(self.origin, "user", axis_order)
            else:
                backends[axis_order] = _get_spatial_reference(self.srid, "epsg", axis_order)

            # Write back in "readonly" format.
            self.__dict__["backends"] = tuple(backends)

        return self.backends[axis_order]

    def _as_proj(self) -> pyproj.CRS:
        """Generate the PROJ CRS object"""
        if (
            isinstance(self.origin, str)
            and not self.origin.isdigit()
            and "epsg.xml#" not in self.origin  # not supported
        ):
            # Passing the origin helps to detect CRS84 strings
            return _get_proj_crs_from_string(self.origin)
        else:
            return _get_proj_crs_from_authority(self.authority, self.srid)

    def apply_to(
        self,
        geometry: AnyGeometry,
        clone=False,
        axis_order: AxisOrder | None = None,
    ) -> AnyGeometry | None:
        """Transform the geometry using this coordinate reference.

        Every transformation within this package happens through this method,
        giving full control over coordinate transformations.

        A bit of background: geometries are provided as ``GEOSGeometry`` from the database.
        This is basically a simple C-based storage implementing "OpenGIS Simple Features for SQL",
        except it does *not* store axis orientation. These are assumed to be x/y.

        To perform transformations, GeoDjango loads the GEOS-geometry into GDAL/OGR.
        The transformed geometry is loaded back to GEOS. To avoid this conversion,
        pass the OGR object directly and continue working on that.

        Internally, this method caches the used GDAL ``CoordTransform`` object,
        so repeated transformations of the same coordinate systems are faster.

        The axis order can change during the transformation.
        From a programming perspective, screen coordinates (x/y) were traditionally used.
        However, various systems and industries have always worked with north/east (y/x).
        This includes systems with critical safety requirements in aviation and maritime.
        The CRS authority reflects this practice. What you need depends on the use case:

        * The (GML) output of WFS 2.0 and WMS 1.3 respect the axis ordering of the CRS.
        * GeoJSON always provides coordinates in x/y, to keep web-based clients simple.
        * PostGIS stores the data in x/y.
        * WFS 1.0 used x/y, WFS 1.3 used y/x except for ``EPSG:4326``.

        When receiving legacy notations (e.g. ``EPSG:4326`` instead of ``urn:ogc:def:crs:EPSG::4326``),
        the data is still projected in legacy ordering, unless ``GISSERVER_FORCE_XY_...`` is disabled.
        This reflects the design of `GeoServer Axis Ordering
        <https://docs.geoserver.org/stable/en/user/services/wfs/axis_order.html>`_
        to have maximum interoperability with legacy/JavaScript clients.

        After GDAL/OGR changed the axis orientation, that information is
        lost when the return value is loaded back into GEOS.
        To address this, :meth:`tag_geometry` is called on the result.

        :param geometry: The GEOS Geometry, or GDAL/OGR loaded geometry.
        :param clone: Whether the object is changed in-place, or a copy is returned.
                      For GEOS->GDAL->GEOS conversions, this makes no difference in efficiency.
        :param axis_order: Which axis ordering to convert the geometry into (depends on the use-case).
        """
        if axis_order is None:
            # This transforms by default to WFS 2 axis ordering (e.g. latitude/longitude),
            # unless a legacy notation is used (e.g. EPSG:4326).
            axis_order = AxisOrder.TRADITIONAL if self.force_xy else AxisOrder.AUTHORITY

        if isinstance(geometry, OGRGeometry):
            transform = _get_coord_transform(geometry.srs, self._as_gdal(axis_order=axis_order))
            return geometry.transform(transform, clone=clone)
        else:
            # See if the geometry was tagged with a CRS.
            # When the data comes from an unknown source, assume this is from database storage.
            # PostGIS stores data in longitude/latitude (x/y) ordering, even for srid 4326.
            # By passing the 'AxisOrder.TRADITIONAL', a conversion from 4326 to 4326
            # with 'AxisOrder.AUTHORITY' will detect that coordinate ordering needs to be changed.
            source_axis_order = getattr(geometry, "_axis_order", AxisOrder.TRADITIONAL)

            if self.srid == geometry.srid and source_axis_order == axis_order:
                # Avoid changes if spatial reference system is identical, and no axis need to change.
                if clone:
                    return geometry.clone()
                else:
                    return None

            # Get GDAL spatial reference for converting coordinates (uses proj internally).
            # Using a cached coordinate transform object (is faster for repeated transforms)
            # The object is also tagged so another apply_to() call would recognize the state.
            source = _get_spatial_reference(geometry.srid, "epsg", source_axis_order)
            target = self._as_gdal(axis_order=axis_order)
            transform = _get_coord_transform(source, target)

            # Transform
            geometry = geometry.transform(transform, clone=clone)
            if clone:
                self.tag_geometry(geometry, axis_order=axis_order)
            return geometry

    @classmethod
    def tag_geometry(self, geometry: GEOSGeometry, axis_order: AxisOrder):
        """Associate this object with the geometry.

        This informs the :meth:`apply_to` method that this source geometry
        already had the correct axis ordering (e.g. it was part of the ``<fes:BBOX>`` logic).
        The srid integer doesn't communicate that information.
        """
        geometry._axis_order = axis_order

    def cache_instance(self):
        """Cache a common CRS, no need to re-instantiate the same object again.
        This also makes sure that requests which use the same URN will get our CRS object
        version, instead of a fresh new one.
        """
        if self.authority == "EPSG" and self.srid != 4326:
            # Only register for EPSG to avoid conflicting axis ordering issues.
            # (WGS84 and CRS84 both use srid 4326, and the 'EPSG:4326' notation is treated as legacy)
            _COMMON_CRS_BY_SRID[self.srid] = self

        _COMMON_CRS_BY_STR[str(self)] = self


#: Worldwide GPS, latitude/longitude (y/x). https://epsg.io/4326
WGS84 = CRS.from_string("urn:ogc:def:crs:EPSG::4326")

#: GeoJSON default. This is like WGS84 but with longitude/latitude (x/y).
CRS84 = CRS.from_string("urn:ogc:def:crs:OGC::CRS84")

#: Spherical Mercator (Google Maps, Bing Maps, OpenStreetMap, ...), see https://epsg.io/3857
WEB_MERCATOR = CRS.from_string("urn:ogc:def:crs:EPSG::3857")


# Register these common ones:
WGS84.cache_instance()
CRS84.cache_instance()
WEB_MERCATOR.cache_instance()
