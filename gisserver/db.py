"""Internal module for additional GIS database functions."""

from __future__ import annotations

import logging
from functools import lru_cache, reduce

from django.contrib.gis.db.models import functions
from django.db import connection, connections, models

from gisserver import conf
from gisserver.geometries import CRS
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
    name = "AsGML"

    def __init__(
        self,
        expression,
        version=3,
        precision=conf.GISSERVER_DB_PRECISION,
        envelope=False,
        **extra,
    ):
        # Note that Django's AsGml, version=2, precision=8
        # the options is postgres-only.
        super().__init__(expression, version, precision, **extra)
        self.envelope = envelope

    def as_postgresql(self, compiler, connection, **extra_context):
        # Fill options parameter (https://postgis.net/docs/ST_AsGML.html)
        options = 33 if self.envelope else 1  # 32 = bbox, 1 = long CRS urn
        template = f"%(function)s(%(expressions)s, {options})"
        return self.as_sql(compiler, connection, template=template, **extra_context)


class ST_Union(functions.Union):
    name = "Union"
    arity = None

    def as_postgresql(self, compiler, connection, **extra_context):
        # PostgreSQL can handle ST_Union(ARRAY[field names]), other databases don't.
        if len(self.source_expressions) > 2:
            extra_context["template"] = "%(function)s(ARRAY[%(expressions)s])"
        return self.as_sql(compiler, connection, **extra_context)


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
                get_db_geometry_target(geo_element, output_crs, use_relative_path=True)
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
