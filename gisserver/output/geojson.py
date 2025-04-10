"""Output rendering logic for GeoJSON."""

from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

import orjson
from django.contrib.gis.db.models.functions import AsGeoJSON
from django.db import models
from django.utils.functional import Promise

from gisserver import conf
from gisserver.db import get_db_geometry_target
from gisserver.projection import FeatureProjection
from gisserver.types import XsdElement

from .base import CollectionOutputRenderer


def _json_default(obj):
    """Serialize non-built in values to JSON"""
    if isinstance(obj, (Decimal, Promise)):
        return str(obj)
    raise TypeError(f"Unable to serialize {obj.__class__.__name__} to JSON")


class GeoJsonRenderer(CollectionOutputRenderer):
    """Fast GeoJSON renderer, using a stream response.

    The complex encoding bits are handled by the C-library "orjson"
    and the geojson property of GEOSGeometry.

    NOTE: While Django has a GeoJSON serializer
    (see https://docs.djangoproject.com/en/3.0/ref/contrib/gis/serializers/),
    it does not offer streaming response handling.
    """

    content_type = "application/geo+json; charset=utf-8"
    content_disposition = 'inline; filename="{typenames} {page} {date}.geojson"'
    max_page_size = conf.GISSERVER_GEOJSON_MAX_PAGE_SIZE
    chunk_size = 40_000

    def decorate_queryset(
        self,
        projection: FeatureProjection,
        queryset: models.QuerySet,
    ):
        """Redefine which fields to query, always include geometry, but remove all others"""
        main_geo_element = projection.feature_type.main_geometry_element
        projection.add_field(main_geo_element)  # make sure geometry is always queried
        queryset = super().decorate_queryset(projection, queryset)

        # Other geometries can be excluded as these are not rendered by 'properties'
        other_geometries = [
            gml_element.orm_path
            for gml_element in projection.geometry_elements
            if gml_element is not main_geo_element
        ]
        if other_geometries:
            queryset = queryset.defer(*other_geometries)

        return queryset

    def render_stream(self):
        self.output = output = BytesIO()

        # Generate the header from a Python dict,
        # but replace the last "}" into a comma, to allow writing more
        header = self.get_header()

        # Have a temporary buffer that is written
        output.write(orjson.dumps(header)[:-1])
        output.write(b',\n  "features": [\n')

        # Flatten the results, they are not grouped in a second FeatureCollection
        is_first_collection = True
        for sub_collection in self.collection.results:
            projection = sub_collection.projection

            if is_first_collection:
                is_first_collection = False
            else:
                output.write(b",\n")

            is_first = True
            for instance in sub_collection:
                if is_first:
                    is_first = False
                else:
                    output.write(b",\n")

                # The "properties" object is generated by orjson.dumps(),
                # while the "geometry" object uses the built-in 'GEOSGeometry.json' result.
                output.write(self.render_feature(projection, instance))

                # Only perform a 'yield' every once in a while,
                # as it goes back-and-forth for writing it to the client.
                if output.tell() > self.chunk_size:
                    json_chunk = output.getvalue()
                    output.seek(0)
                    output.truncate(0)
                    yield json_chunk

        # Instead of performing an expensive .count() on the start of the page,
        # write this as a last field at the end of the response.
        # This still honors the WFS 30 DRAFT without sacrificing performance.
        output.write(b"\n  ],\n")
        footer = self.get_footer()
        output.write(orjson.dumps(footer)[1:])
        output.write(b"\n")
        yield output.getvalue()

    def render_exception(self, exception: Exception):
        """Render the exception in a format that fits with the output."""
        message = super().render_exception(exception)
        buffer = self.output.getvalue().decode()
        return f"{buffer}/* {message} */\n"

    def render_feature(self, projection: FeatureProjection, instance: models.Model) -> bytes:
        """Render the output of a single feature"""

        # Get all instance attributes:
        properties = self.get_properties(projection, projection.xsd_root_elements, instance)
        feature_type = projection.feature_type

        # Add the name field
        if feature_type.show_name_field:
            name = feature_type.get_display_value(instance)
            json_geometry_name = b'"geometry_name":%b,' % orjson.dumps(name)
        else:
            json_geometry_name = b""

        return b'    {"type":"Feature","id":%b,%b"geometry":%b,"properties":%b}' % (
            orjson.dumps(f"{feature_type.name}.{instance.pk}"),
            json_geometry_name,
            self.render_geometry(projection, instance),
            orjson.dumps(properties, default=_json_default),
        )

    def _format_geojson_value(self, value):
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        elif isinstance(value, models.Model):
            # ForeignKey, not defined as complex type.
            return str(value)
        else:
            return value

    def render_geometry(self, projection: FeatureProjection, instance: models.Model) -> bytes:
        """Generate the proper GeoJSON notation for a geometry.
        This calls the GDAL C-API rendering found in 'GEOSGeometry.json'
        """
        geometry = projection.get_main_geometry_value(instance)
        if geometry is None:
            return b"null"

        projection.output_crs.apply_to(geometry)
        return geometry.json.encode()

    def get_header(self) -> dict:
        """Generate the header fields.

        The format is based on the WFS 3.0 DRAFT. The count fields are moved
        to the footer allowing them to be calculated without performing queries.
        """
        output_crs = self.collection.results[0].projection.output_crs
        return {
            "type": "FeatureCollection",
            "timeStamp": self._format_geojson_value(self.collection.timestamp),
            # "numberReturned": is written at the end for better query performance.
            "crs": {"type": "name", "properties": {"name": str(output_crs)}},
        }

    def get_footer(self) -> dict:
        """Generate the last fields of the response.
        By moving the links, numberReturned/numberMatched fields to the end,
        it's not always needed to perform queries to calculate these.

        The format is based on the WFS 3.0 DRAFT which defines the extra
        pagination headers and numberMatched/numberReturned headers.
        While the draft suggests to put these fields first, there is no such
        requirement in JSON.
        """
        return {
            "links": self.get_links(),
            "numberReturned": self.collection.number_returned,
            "numberMatched": self.collection.number_matched,
        }

    def get_links(self) -> list:
        """Generate the pagination links"""
        links = []
        if self.collection.next:
            links.append(
                {
                    "href": self.collection.next,
                    "rel": "next",
                    "type": "application/geo+json",
                    "title": "next page",
                }
            )
        if self.collection.previous:
            links.append(
                {
                    "href": self.collection.previous,
                    "rel": "previous",
                    "type": "application/geo+json",
                    "title": "previous page",
                }
            )
        return links

    def get_properties(
        self, projection: FeatureProjection, xsd_elements: list[XsdElement], instance: models.Model
    ) -> dict:
        """Collect the data for the 'properties' field.

        This is based on the original XSD definition,
        so the rendering is consistent with other output formats.

        :param projection: Overview of all fields to render.
        :param xsd_elements: The XSD elements to render.
        :param instance: The object instance.
        """
        props = {}
        for xsd_element in xsd_elements:
            if not xsd_element.type.is_geometry:
                value = xsd_element.get_value(instance)
                if xsd_element.type.is_complex_type:
                    # Nested object data
                    if value is None:
                        props[xsd_element.name] = None
                    else:
                        sub_elements = projection.xsd_child_nodes[xsd_element]
                        if xsd_element.is_many:
                            # "..._to_many relation; reverse FK, M2M or array field.
                            props[xsd_element.name] = [
                                self.get_properties(projection, sub_elements, item)
                                for item in value
                            ]
                        else:
                            props[xsd_element.name] = self.get_properties(
                                projection, sub_elements, value
                            )
                else:
                    # Scalar value, or list (for ArrayField).
                    props[xsd_element.name] = self._format_geojson_value(value)

        return props


class DBGeoJsonRenderer(GeoJsonRenderer):
    """GeoJSON renderer that relays the geometry rendering to the database.

    This is even more efficient than calling the C-API for each feature.
    """

    def decorate_queryset(self, projection: FeatureProjection, queryset):
        """Update the queryset to let the database render the GML output.
        This is far more efficient than GeoDjango's logic, which performs a
        C-API call for every single coordinate of a geometry.
        """
        queryset = super().decorate_queryset(projection, queryset)
        # If desired, the entire FeatureCollection could be rendered
        # in PostgreSQL as well: https://postgis.net/docs/ST_AsGeoJSON.html
        main_geo_element = projection.feature_type.main_geometry_element
        if main_geo_element is not None:
            queryset = queryset.defer(main_geo_element.orm_path).annotate(
                _as_db_geojson=AsGeoJSON(
                    get_db_geometry_target(main_geo_element, projection.output_crs),
                    precision=conf.GISSERVER_DB_PRECISION,
                )
            )

        return queryset

    def render_geometry(self, projection: FeatureProjection, instance: models.Model) -> bytes:
        """Generate the proper GeoJSON notation for a geometry"""
        # Database server rendering
        if projection.main_geometry_element is None:
            return b"null"

        geojson = instance._as_db_geojson
        return b"null" if geojson is None else geojson.encode()
