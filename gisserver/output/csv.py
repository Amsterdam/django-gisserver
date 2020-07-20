"""Output rendering logic for GeoJSON."""
import csv
from datetime import datetime
from typing import List

from django.conf import settings
from django.db import models
from django.utils.timezone import utc

from gisserver import conf
from gisserver.db import (
    AsEWKT,
    build_db_annotations,
    get_db_annotation,
    get_db_geometry_selects,
)
from gisserver.features import FeatureType
from gisserver.types import XsdComplexType, XsdElement
from .base import (
    OutputRenderer,
    StringBuffer,
)


class CSVRenderer(OutputRenderer):
    """Fast CSV renderer, using a stream response.

    The complex encoding bits are handled by the "csv" library.
    """

    content_type = "text/csv; charset=utf-8"
    max_page_size = conf.GISSERVER_CSV_MAX_PAGE_SIZE
    dialect = "unix"

    @classmethod
    def decorate_queryset(
        cls, feature_type: FeatureType, queryset, output_crs, **params
    ):
        """Make sure relations are included with select-related to avoid N-queries.
        Using prefetch_related() isn't possible with .iterator().
        """
        xsd_type: XsdComplexType = feature_type.xsd_type
        # Take all relations that are expanded to complex elements,
        # and all relations that are fetched for flattened elements.
        related = set(
            xsd_element.orm_path for xsd_element in xsd_type.complex_elements
        ) | set(
            xsd_element.orm_relation[0] for xsd_element in xsd_type.flattened_elements
        )
        if related:
            queryset = queryset.select_related(*related)

        return queryset

    def render_stream(self):
        output = StringBuffer()
        writer = csv.writer(output, dialect=self.dialect)

        is_first_collection = True
        for sub_collection in self.collection.results:
            if is_first_collection:
                is_first_collection = False
            else:
                # Multiple feature types requested, add newlines to separate them
                output.write(b"\n\n")

            # Write the header
            fields = [f for f in sub_collection.feature_type.xsd_type.elements]
            writer.writerow(self.get_header(fields))

            # By using .iterator(), the results are streamed with as little memory as
            # possible. Doing prefetch_related() is not possible now. That could only
            # be implemented with cursor pagination for large sets for 1000+ results.
            for instance in sub_collection.iterator():
                writer.writerow(self.get_row(instance, fields))

                # Only perform a 'yield' every once in a while,
                # as it goes back-and-forth for writing it to the client.
                if output.is_full():
                    yield output.getvalue()
                    output.clear()

        yield output.getvalue()

    def render_exception(self, exception: Exception):
        """Render the exception in a format that fits with the output."""
        if settings.DEBUG:
            return f"\n\n{exception.__class__.__name__}: {exception}\n"
        else:
            return f"\n\n{exception.__class__.__name__} during rendering!\n"

    def get_header(self, fields: List[XsdElement]) -> List[str]:
        """Return all field names."""
        names = []
        append = names.append
        for field in fields:
            if field.type.is_complex_type:
                # Expand complex types
                for sub_field in field.type.elements:
                    append(f"{field.name}.{sub_field.name}")
            else:
                append(field.name)

        return names

    def get_row(self, instance: models.Model, fields: List[XsdElement]):
        """Return all field values for a single row."""
        values = []
        append = values.append
        for field in fields:
            if field.is_geometry:
                append(self.render_geometry(instance, field))
                continue

            value = field.get_value(instance)
            if field.type.is_complex_type:
                for sub_field in field.type.elements:
                    append(sub_field.get_value(value))
            elif isinstance(value, list):
                # Array field
                append(",".join(map(str, value)))
            elif isinstance(value, datetime):
                append(str(value.astimezone(utc)))
            else:
                append(value)
        return values

    def render_geometry(self, instance: models.Model, field: XsdElement):
        """Render the contents of a geometry value."""
        return field.get_value(instance)


class DBCSVRenderer(CSVRenderer):
    """Further optimized CSV renderer that uses the database to render EWKT.
    This is about 40% faster then calling the GEOS C-API from python.
    """

    @classmethod
    def decorate_queryset(cls, feature_type, queryset, output_crs, **params):
        queryset = super().decorate_queryset(
            feature_type, queryset, output_crs, **params
        )

        # Instead of reading the binary geometry data,
        # ask the database to generate EWKT data directly.
        geometries = get_db_geometry_selects(
            feature_type.xsd_type.geometry_elements, output_crs
        )
        if geometries:
            queryset = queryset.defer(*geometries.keys()).annotate(
                **build_db_annotations(geometries, "_as_ewkt_{name}", AsEWKT)
            )

        return queryset

    def render_geometry(self, instance: models.Model, field: XsdElement):
        return get_db_annotation(instance, field.name, "_as_ewkt_{name}")
