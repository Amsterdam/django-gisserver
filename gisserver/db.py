"""Internal module for additional GIS database functions."""
from __future__ import annotations

from functools import reduce
from typing import cast

from django.contrib.gis.db.models import GeometryField, functions
from django.db import connection, connections, models

from gisserver import conf
from gisserver.geometries import CRS
from gisserver.types import XPathMatch, XsdElement


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
        # PostgreSQL can handle ST_Union(ARRAY(field names)), other databases don't.
        if len(self.source_expressions) > 2:
            extra_context["template"] = "%(function)s(ARRAY(%(expressions)s))"
        return self.as_sql(compiler, connection, **extra_context)


def get_geometries_union(
    expressions: list[str | functions.GeoFunc], using="default"
) -> str | functions.Union:
    """Generate a union of multiple geometry fields."""
    if not expressions:
        raise ValueError("Missing geometery fields for get_geometries_union()")

    if len(expressions) == 1:
        return next(iter(expressions))  # fastest in set data type
    elif len(expressions) == 2:
        return functions.Union(*expressions)
    elif connections[using].vendor == "postgresql":
        # postgres can handle multiple field names
        return ST_Union(expressions)
    else:
        # other databases do Union(Union(1, 2), 3)
        return reduce(functions.Union, expressions)


def conditional_transform(
    expression: str | functions.GeoFunc, expression_srid: int, output_srid: int
) -> str | functions.Transform:
    """Apply a CRS Transform to the queried field if that is needed."""
    if expression_srid != output_srid:
        expression = functions.Transform(expression, srid=output_srid)
    return expression


def build_db_annotations(
    selects: dict[str, str | functions.Func],
    name_template: str,
    wrapper_func: type[functions.Func],
) -> dict:
    """Utility to build annotations for all geometry fields for an XSD type.
    This is used by various DB-optimized rendering methods.
    """
    return {
        escape_xml_name(name, name_template): wrapper_func(target)
        for name, target in selects.items()
    }


def get_db_annotation(instance: models.Model, name: str, name_template: str):
    """Retrieve the value that an annotation has added to the model."""
    # The "name" allows any XML-tag elements, escape the most obvious
    escaped_name = escape_xml_name(name, name_template)
    try:
        return getattr(instance, escaped_name)
    except AttributeError as e:
        raise AttributeError(
            f" DB annotation {instance._meta.model_name}.{escaped_name}"
            f" not found (using {name_template})"
        ) from e


def escape_xml_name(name: str, template="{name}") -> str:
    """Escape an XML name to be used as annotation name."""
    return template.format(name=name.replace(".", "_"))


def get_db_geometry_selects(
    gml_elements: list[XsdElement], output_crs: CRS
) -> dict[str, str | functions.Transform]:
    """Utility to generate select clauses for the geometry fields of a type.
    Key is the xsd element name, value is the database select expression.
    """
    return {
        xsd_element.name: _get_db_geometry_target(xsd_element, output_crs)
        for xsd_element in gml_elements
        if xsd_element.source is not None
    }


def _get_db_geometry_target(
    xsd_element: XsdElement, output_crs: CRS
) -> str | functions.Transform:
    """Wrap the selection of a geometry field in a CRS Transform if needed."""
    field = cast(GeometryField, xsd_element.source)
    return conditional_transform(
        xsd_element.orm_path, field.srid, output_srid=output_crs.srid
    )


def get_db_geometry_target(xpath_match: XPathMatch, output_crs: CRS):
    """Based on a resolved element, build the proper geometry field select clause."""
    field = cast(GeometryField, xpath_match.child.source)
    return conditional_transform(
        xpath_match.orm_path, field.srid, output_srid=output_crs.srid
    )
