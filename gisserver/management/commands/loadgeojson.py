"""Quick utility to import GeoJSON data in the Django project."""

from __future__ import annotations

import json
import operator
from argparse import ArgumentTypeError
from functools import reduce
from itertools import islice
from urllib.request import urlopen

from django.apps import apps
from django.contrib.gis.db.models import GeometryField
from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import FieldDoesNotExist
from django.core.management import BaseCommand, CommandError, CommandParser
from django.db import DEFAULT_DB_ALIAS, connections, models, transaction

from gisserver.crs import CRS, CRS84


def _parse_model(value):
    try:
        return apps.get_model(value)
    except LookupError as e:
        raise ArgumentTypeError(str(e)) from e


def _parse_fields(value):
    field_map = {}
    for pair in value.split(","):
        geojson_name, _, field_name = pair.strip().partition("=")
        if not field_name:
            raise ArgumentTypeError("Expect property=field,property2=field2 format")
        field_map[geojson_name] = field_name
    return field_map


class Command(BaseCommand):
    """Quick command to import data in the WFS server."""

    help = (
        "Import GeoJSON data into a WFS feature collection. This can be done using:"
        "  manage.py loadgeojson --model=places.Province"
        " -f name=name,prop2=field2 --geometry-field geometry provinces.json"
    )

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            choices=tuple(connections),
            help=(
                "Nominates a specific database to load fixtures into. Defaults to the "
                '"default" database.'
            ),
        )
        parser.add_argument(
            "-m",
            "--model",
            required=True,
            metavar="MODEL",
            type=_parse_model,
            help="Django model, in the format: app_label.ModelName.",
        )
        parser.add_argument(
            "-g",
            "--geometry-field",
            required=False,
            metavar="NAME",
            help="Name of the model's geometry field, auto-detected if not specified.",
        )
        parser.add_argument(
            "-f",
            "--field",
            action="append",
            dest="map_fields",
            type=_parse_fields,
            metavar="NAME=FIELD",
            help=(
                "Map GeoJSON properties to Django fields, in the format: property1=field1,property2=field2,... "
                "By default, this autodetects common field names only. "
                "Explicitly ignore fields by using -f property=,property2=field2."
            ),
        )
        parser.add_argument(
            "geojson-file",
            help="GeoJSON file or URL to import. For debugging, it's better to download the file first.",
        )

    def handle(self, *args, **options):
        # Get arguments
        self.using = options["database"]
        self.connection = connections[self.using]
        model: type[models.Model] = options["model"]
        main_geometry_field = self._get_geometry_field(model, options["geometry_field"])
        field_map = self._parse_field_map(model, options["map_fields"])

        # Read the file
        geojson = self._load_geojson(options["geojson-file"])
        if not geojson["features"]:
            self.stdout.write(self.style.NOTICE("Empty GeoJSON data"))
            return

        # See if properties match the Django field names, use those too.
        # (unless these are mapped already via the command line args).
        field_map.update(self._get_auto_field_map(model, geojson["features"][0], field_map))

        # See if a CRS is declared
        self.crs = self._read_crs(geojson)

        # Import in chunks
        num_imported = 0
        id_field = model._meta.pk.name
        with transaction.atomic(using=self.using):
            features = iter(self._read_geojson(geojson, model, main_geometry_field, field_map))
            while batch := list(islice(features, 100)):
                if id_field in batch[0]:
                    # The ID field is provided, allow "on conflict update..."
                    unique_fields = [id_field]
                    update_fields = list(batch[0].keys())
                    update_fields.remove(id_field)

                    model.objects.using(self.using).bulk_create(
                        [model(**values) for values in batch],
                        update_conflicts=True,
                        unique_fields=unique_fields,
                        update_fields=update_fields,
                    )
                else:
                    model.objects.using(self.using).bulk_create(
                        [model(**values) for values in batch]
                    )

                num_imported += len(batch)

        self.stdout.write(f"Installed {num_imported} feature(s)")

    def _get_geometry_field(self, model: type[models.Model], field_name: str | None):
        """Find the geometry field name, or validate it."""
        if field_name:
            # Field is given in CLI args, validate it.
            try:
                field = model._meta.get_field(field_name)
            except FieldDoesNotExist as e:
                raise CommandError(f"Invalid value for --geometry-field: {e}") from e

            if not isinstance(field, GeometryField):
                raise CommandError("Invalid value for --geometry-field: not a GeometryField")
        else:
            # Field is not given, auto-detect
            try:
                field_name = next(
                    f.name for f in model._meta.fields if isinstance(f, GeometryField)
                )
            except StopIteration:
                raise CommandError(
                    f"Model {model._meta.label} does not have any GeometryField member."
                ) from None

        return field_name

    def _load_geojson(self, filename) -> dict:
        """Parse and validate the GeoJSON data into Python dict data."""
        try:
            if "://" in filename:
                with urlopen(filename, timeout=60) as response:  # noqa: S310
                    geojson = json.load(response)
            else:
                with open(filename) as fh:
                    geojson = json.load(fh)
        except OSError as e:  # FileNotFoundError or HTTP errors
            raise CommandError(str(e)) from e
        except (ValueError, TypeError) as e:
            raise CommandError(f"Unable to parse GeoJSON: {e}") from e

        if (
            not isinstance(geojson, dict)
            or geojson.get("type") != "FeatureCollection"
            or "features" not in geojson
        ):
            raise CommandError("Invalid GeoJSON data, expected FeatureCollection element.")

        return geojson

    def _read_crs(self, geojson: dict) -> CRS:
        """Find the CRS that should be used for all geometry data."""
        crs = geojson.get("crs")
        if not crs:
            return CRS84  # default for GeoJSON

        try:
            type = crs["type"]
            if type == "name":
                return CRS.from_string(crs["properties"]["name"])
            else:
                # type 'link' with subtype 'proj4/ogcwkt/esriwkt' are not handled here.
                raise CommandError(f"CRS type {type} is not supported.")
        except KeyError as e:
            raise CommandError(f"CRS is invalid, missing '{e}' field") from e

    def _parse_field_map(self, model, map_fields: list[dict]) -> dict:
        """Validate that the provided field mapping points to model fields."""
        if not map_fields:
            return {}

        field_map: dict = reduce(operator.or_, map_fields)
        for field_name in field_map.values():
            try:
                model._meta.get_field(field_name)
            except FieldDoesNotExist as e:
                raise CommandError(f"Field '{field_name}' does not exist in Django model.") from e

        return field_map

    def _get_auto_field_map(self, model, feature: dict, field_map: dict):
        """Autodetect which properties match model field names."""
        auto_field_map = {}
        for geojson_name in feature.get("properties", ()):
            if geojson_name in field_map:
                continue

            try:
                model._meta.get_field(geojson_name)
            except FieldDoesNotExist:
                msg = (
                    f"GeoJSON property '{geojson_name}' is not mapped nor exists in Django model, skipping."
                    if field_map
                    else f"GeoJSON property '{geojson_name}' does not exist in Django model, skipping."
                )
                self.stderr.write(self.style.WARNING(msg))
            else:
                self.stdout.write(
                    f"GeoJSON property '{geojson_name}' also exists as Django model field, using."
                )
                auto_field_map[geojson_name] = geojson_name

        return auto_field_map

    def _read_geojson(
        self, geojson: dict, model: type[models.Model], main_geometry_field: str, field_map: dict
    ):
        """Convert the GeoJSON data to model field names."""
        pk_field = model._meta.pk.name

        for feature in geojson["features"]:
            # Validate basic layout
            try:
                feature_type = feature["type"]
                geometry_data = feature["geometry"]
            except KeyError as e:
                raise CommandError(f"Feature does not have required '{e}' element.") from e
            if feature_type != "Feature":
                raise CommandError(f"Expected 'Feature', not {feature_type}")

            # Collect all fields
            properties = feature.get("properties", {})
            field_values = {
                field_name: self._parse_value(
                    model._meta.get_field(field_name), properties.get(geojson_name)
                )
                for geojson_name, field_name in field_map.items()
                if field_name
            }

            # Store the geometry, note GEOS only parses stringified JSON.
            if geometry_data is None:
                geometry = None
            else:
                try:
                    # NOTE: this looses the axis ordering information,
                    # and assumes x/y as the standard prescribes.
                    geometry = GEOSGeometry(json.dumps(geometry_data), srid=self.crs.srid)
                except ValueError as e:
                    raise CommandError(
                        f"Unable to parse geometry data: {geometry_data!r}: {e}"
                    ) from e
                geometry.srid = self.crs.srid  # override default

            field_values[main_geometry_field] = geometry

            # Try to decode the identifier if it's present
            if (
                pk_field not in field_values
                and (raw_value := feature.get("id")) is not None
                and (id_value := self._parse_id(model._meta.pk, raw_value)) is not None
            ):
                field_values[pk_field] = id_value

            # Pass as Django model fields
            yield field_values

    def _parse_id(self, pk_field: models.Field, id_value):
        # Allow TypeName.id format, see if it parses
        try:
            return pk_field.get_db_prep_save(
                id_value.rpartition(".")[2], connection=self.connection
            )
        except (ValueError, TypeError):
            self.stderr.write(
                self.style.WARNING(
                    f"Feature id value '{id_value}' can't be stored in the primary key field. ignoring."
                )
            )
            return None

    def _parse_value(self, field: models.Field, value):
        try:
            return field.get_db_prep_save(value, connection=self.connection)
        except (ValueError, TypeError) as e:
            raise CommandError(f"Can't parse {value!r} in model field '{field.name}': {e}.") from e
