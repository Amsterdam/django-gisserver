"""Output rendering logic for GeoJSON."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO

from django.db import models

from gisserver import conf
from gisserver.db import AsEWKT, get_db_rendered_geometry, replace_queryset_geometries
from gisserver.projection import FeatureProjection, FeatureRelation
from gisserver.types import GeometryXsdElement, XsdElement, XsdTypes

from .base import CollectionOutputRenderer


class CSVRenderer(CollectionOutputRenderer):
    """Fast CSV renderer, using a stream response.

    The complex encoding bits are handled by the "csv" library.
    """

    content_type = "text/csv; charset=utf-8"
    content_disposition = 'attachment; filename="{typenames} {page} {date}.csv"'
    max_page_size = conf.GISSERVER_CSV_MAX_PAGE_SIZE
    chunk_size = 40_000

    #: The outputted CSV dialect. This can be a csv.Dialect subclass
    #: or one of the registered names like: "unix", "excel", "excel-tab"
    dialect = "unix"

    def decorate_queryset(
        self, projection: FeatureProjection, queryset: models.QuerySet
    ) -> models.QuerySet:
        """Make sure relations are included with select-related to avoid N-queries.
        Using prefetch_related() isn't possible with .iterator().
        """
        # First, make sure no array or m2m elements exist,
        # as these are not possible to render in CSV.
        projection.remove_fields(
            lambda e: (e.is_many and not e.is_array)
            or e.type == XsdTypes.gmlCodeType  # gml:name
            or e.type == XsdTypes.gmlBoundingShapeType  # gml:boundedBy
        )

        # All database optimizations
        return super().decorate_queryset(projection, queryset)

    def render_stream(self):
        self.output = output = StringIO()
        writer = csv.writer(output, dialect=self.dialect)

        is_first_collection = True
        for sub_collection in self.collection.results:
            projection = sub_collection.projection
            if is_first_collection:
                is_first_collection = False
            else:
                # Multiple feature types requested, add newlines to separate them
                output.write("\n\n")

            # Write the header
            xsd_elements = projection.xsd_root_elements
            writer.writerow(self.get_header(projection, xsd_elements))

            # Write all rows
            for instance in self.read_features(sub_collection):
                writer.writerow(self.get_row(instance, projection, xsd_elements))

                # Only perform a 'yield' every once in a while,
                # as it goes back-and-forth for writing it to the client.
                if output.tell() > self.chunk_size:
                    csv_chunk = output.getvalue()
                    output.seek(0)
                    output.truncate(0)
                    yield csv_chunk

        yield output.getvalue()

    def render_exception(self, exception: Exception):
        """Render the exception in a format that fits with the output."""
        message = super().render_exception(exception)
        buffer = self.output.getvalue()
        return f"{buffer}\n\n{message}\n"

    def get_header(
        self, projection: FeatureProjection, xsd_elements: list[XsdElement], prefix=""
    ) -> list[str]:
        """Return all field names."""
        names = []
        append = names.append
        for xsd_element in xsd_elements:
            if xsd_element.type.is_complex_type:
                names.extend(
                    self.get_header(
                        projection,
                        xsd_elements=projection.xsd_child_nodes[xsd_element],
                        prefix=f"{prefix}{xsd_element.name}.",
                    )
                )
            else:
                append(f"{prefix}{xsd_element.name}")

        return names

    def get_row(
        self, instance: models.Model, projection: FeatureProjection, xsd_elements: list[XsdElement]
    ):
        """Return all field values for a single row."""
        values = []
        append = values.append
        for xsd_element in xsd_elements:
            if xsd_element.type.is_geometry:
                append(self.render_geometry(projection, instance, xsd_element))
                continue

            value = xsd_element.get_value(instance)
            if xsd_element.type.is_complex_type:
                values.extend(
                    self.get_row(
                        instance=value,
                        projection=projection,
                        xsd_elements=projection.xsd_child_nodes[xsd_element],
                    )
                )
            elif isinstance(value, list):
                # Array field
                append(",".join(map(str, value)))
            elif isinstance(value, datetime):
                append(str(value.astimezone(timezone.utc)))
            else:
                append(value)
        return values

    def render_geometry(
        self,
        projection: FeatureProjection,
        instance: models.Model,
        geo_element: GeometryXsdElement,
    ) -> str:
        """Render the contents of a geometry value."""
        geometry = geo_element.get_value(instance)
        projection.output_crs.apply_to(geometry)
        return geometry.ewkt


class DBCSVRenderer(CSVRenderer):
    """Further optimized CSV renderer that uses the database to render EWKT.
    This is about 40% faster than calling the GEOS C-API from python.
    """

    def decorate_queryset(
        self, projection: FeatureProjection, queryset: models.QuerySet
    ) -> models.QuerySet:
        # Instead of reading the binary geometry data, let the database generate EWKT data.
        # As annotations can't be done for select_related() objects, prefetches are used instead.
        queryset = super().decorate_queryset(projection, queryset)
        return replace_queryset_geometries(
            queryset, projection.geometry_elements, projection.output_crs, AsEWKT
        )

    def get_prefetch_queryset(
        self, projection: FeatureProjection, feature_relation: FeatureRelation
    ) -> models.QuerySet | None:
        """Perform DB annotations for prefetched relations too."""
        queryset = super().get_prefetch_queryset(projection, feature_relation)
        if queryset is None:
            return None

        # Find which fields are GML elements, annotate these too.
        return replace_queryset_geometries(
            queryset, feature_relation.geometry_elements, projection.output_crs, AsEWKT
        )

    def render_geometry(
        self,
        projection: FeatureProjection,
        instance: models.Model,
        geo_element: GeometryXsdElement,
    ):
        """Render the geometry using a database-rendered version."""
        return get_db_rendered_geometry(instance, geo_element, AsEWKT)
