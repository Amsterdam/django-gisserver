"""Internal module for additional GIS database functions."""

from __future__ import annotations

import logging
from functools import lru_cache, reduce

from django.contrib.gis.db.models import Extent, PolygonField, functions
from django.contrib.gis.db.models.fields import ExtentField
from django.db import connection, connections, models

from gisserver import conf
from gisserver.crs import CRS, WGS84
from gisserver.geometries import WGS84BoundingBox
from gisserver.types import GeometryXsdElement

logger = logging.getLogger(__name__)


class AsEWKT(functions.GeoFunc):
    """Generate EWKT in the database (PostGIS tested only at the moment)."""

    name = "AsEWKT"
    output_field = models.TextField()

    def __init__(self, field, precision=conf.GISSERVER_DB_PRECISION, **extra):
        if connection.ops.spatial_version >= (3, 1):
            super().__init__(field, precision, **extra)
        else:
            super().__init__(field, **extra)


class AsGML(functions.AsGML):
    """An overwritten ST_AsGML() function to handle PostGIS extensions."""

    name = "AsGML"

    def __init__(
        self,
        expression,
        version=3,
        precision=conf.GISSERVER_DB_PRECISION,
        envelope=False,
        is_latlon=False,
        long_urn=False,
        **extra,
    ):
        # Note that Django's AsGml the defaults are: version=2, precision=8
        super().__init__(expression, version, precision, **extra)
        self.envelope = envelope
        self.is_latlon = is_latlon
        self.long_urn = long_urn

    def as_postgresql(self, compiler, connection, **extra_context):
        # Fill options parameter (https://postgis.net/docs/ST_AsGML.html)
        options = 0
        if self.long_urn:
            options |= 1  # long CRS urn
        if self.envelope:
            options |= 32  # bbox
        if self.is_latlon:
            # PostGIS provides the data in longitude/latitude format (east/north to look like x/y).
            # However, WFS 2.0 fixed their axis by following the authority. The ST_AsGML() doesn't
            # detect this on their own. It needs to be told to flip the coordinates.
            # Passing option 16 flips the coordinates unconditionally, like using ST_FlipCoordinates()
            # but more efficiently done during rendering. That happens in:
            # https://github.com/postgis/postgis/blob/81e2bc783b77cc740291445e992658e1db7179e0/liblwgeom/lwout_gml.c#L121
            options |= 16

        template = f"%(function)s(%(expressions)s, {options})"
        return self.as_sql(compiler, connection, template=template, **extra_context)


class ST_SetSRID(functions.Transform):
    """PostGIS function to assign an SRID to geometry.
    When this is applied to the result from an ``Extent`` aggegrate,
    it will convert that ``BBOX(...)`` value into a ``POLYGON(...)``.
    """

    name = "SetSRID"
    geom_param_pos = ()

    @property
    def geo_field(self):
        return PolygonField(srid=self.source_expressions[1].value)


class Box2D(functions.GeomOutputGeoFunc):
    """PostGIS function (without ST_) that converts a ``POLYGON(...)`` back to a ``BOX(...)``."""

    name = "Box2D"
    function = "Box2D"  # no ST_ prefix.
    output_field = ExtentField()

    def convert_value(self, value, expression, connection):
        return connection.ops.convert_extent(value)


class ST_Union(functions.Union):
    name = "Union"
    arity = None

    def as_postgresql(self, compiler, connection, **extra_context):
        # PostgreSQL can handle ST_Union(ARRAY[field names]), other databases don't.
        if len(self.source_expressions) > 2:
            extra_context["template"] = "%(function)s(ARRAY[%(expressions)s])"
        return self.as_sql(compiler, connection, **extra_context)


def get_wgs84_bounding_box(
    queryset: models.QuerySet, geo_element: GeometryXsdElement
) -> WGS84BoundingBox:
    """Calculate the WGS84 bounding box for a feature.

    Note that the ``<ows:WGS84BoundingBox>`` element
    always uses longitude/latitude, and doesn't describe a CRS.
    """
    if connections[queryset.db].vendor == "postgresql":
        # Allow a more efficient way to combine geometry first, transform once later
        box = queryset.aggregate(
            box=Box2D(
                functions.Transform(
                    ST_SetSRID(Extent(geo_element.orm_path), srid=geo_element.source_srid),
                    srid=WGS84.srid,
                )
            )
        )["box"]
    else:
        # Need to transform each element to srid 4326 before combining it in an extent.
        box = queryset.aggregate(box=Extent(get_db_geometry_target(geo_element, WGS84)))["box"]

    return WGS84BoundingBox(*box) if box else None


def get_geometries_union(
    expressions: list[str | functions.GeoFunc], using="default"
) -> str | functions.Union:
    """Generate a union of multiple geometry fields."""
    if not expressions:
        raise ValueError("Missing geometry fields for get_geometries_union()")

    if len(expressions) == 1:
        return next(iter(expressions))  # fastest in set data type
    elif len(expressions) == 2:
        return functions.Union(*expressions)
    elif connections[using].vendor == "postgresql":
        # postgres can handle multiple field names
        return ST_Union(*expressions)
    else:
        # other databases do Union(Union(1, 2), 3)
        return reduce(functions.Union, expressions)


def replace_queryset_geometries(
    queryset: models.QuerySet,
    geo_elements: list[GeometryXsdElement],
    output_crs: CRS,
    wrapper_func: type[functions.GeoFunc],
    **wrapper_kwargs,
) -> models.QuerySet:
    """Replace the queryset geometry retrieval with a database-rendered version.

    This uses absolute paths in the queryset, but can use relative paths for related querysets.
    """
    defer_names = []
    as_geo_map = {}
    for geo_element in geo_elements:
        if geo_element.source is not None:  # excludes GmlBoundedByElement
            defer_names.append(geo_element.local_orm_path)
            annotation_name = _as_annotation_name(geo_element.local_orm_path, wrapper_func)
            as_geo_map[annotation_name] = wrapper_func(
                get_db_geometry_target(geo_element, output_crs, use_relative_path=True),
                **wrapper_kwargs,
            )

    if not defer_names:
        return queryset

    logger.debug(
        "DB rendering: QuerySet for %s replacing %r with %r",
        queryset.model._meta.label,
        defer_names,
        list(as_geo_map.keys()),
    )
    return queryset.defer(*defer_names).annotate(**as_geo_map)


def get_db_rendered_geometry(
    instance: models.Model, geo_element: GeometryXsdElement, replacement: type[functions.GeoFunc]
) -> str:
    """Retrieve the database-rendered geometry.
    This includes formatted EWKT or GML output, rendered by the database.
    """
    annotation_name = _as_annotation_name(geo_element.local_orm_path, replacement)
    try:
        return getattr(instance, annotation_name)
    except AttributeError as e:
        prefix = _as_annotation_name("", replacement)
        available = ", ".join(key for key in instance.__dict__ if key.startswith(prefix)) or "none"
        raise AttributeError(
            f" DB annotation {instance._meta.label}.{annotation_name} not found. Found {available}."
        ) from e


@lru_cache
def _as_annotation_name(name: str, func: type[functions.GeoFunc]) -> str:
    """Escape an XML name to be used as annotation name."""
    return f"_{func.__name__}_{name.replace('.', '_')}"


def get_db_geometry_target(
    geo_element: GeometryXsdElement, output_crs: CRS, use_relative_path: bool = False
) -> str | functions.Transform:
    """Translate a GML geometry field into the proper expression for retrieving it from the database.
    The path will be wrapped into a CRS Transform function if needed.
    """
    orm_path = geo_element.local_orm_path if use_relative_path else geo_element.orm_path
    if geo_element.source_srid != output_crs.srid:
        return functions.Transform(orm_path, srid=output_crs.srid)
    else:
        return orm_path
