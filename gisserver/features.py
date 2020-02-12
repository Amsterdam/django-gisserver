"""Dataclasses that expose the metadata for the GetCapabilities call."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import inf
from typing import List, Optional, Tuple, Type

from django.contrib.gis.db.models import Extent, GeometryField
from django.contrib.gis.db.models.functions import Transform
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.functional import cached_property  # py3.8: functools

from gisserver.types import CRS, WGS84, BoundingBox


@dataclass
class ServiceDescription:
    """Basic metadata for an exposed GIS service."""

    title: str
    abstract: Optional[str] = None
    keywords: Optional[List[str]] = None

    provider_name: Optional[str] = None
    provider_site: Optional[str] = None
    contact_person: Optional[str] = None


@dataclass
class FeatureType:
    """Declare a feature that is exposed on the map.

    This corresponds with a single Django model.
    """

    model: Type[models.Model]
    geometry_field_name: str = None

    # WFS Metadata:
    name: str = None
    title: str = None
    abstract: str = None
    keywords: List[str] = field(default_factory=list)
    crs: CRS = None
    other_crs: List[CRS] = field(default_factory=list)
    metadata_url: Optional[str] = None

    def __post_init__(self):
        # Add some defaults
        if not self.name:
            self.name = self.model._meta.model_name
        if not self.title:
            self.title = self.model._meta.verbose_name

        self.geometry_fields = [
            f for f in self.model._meta.get_fields() if isinstance(f, GeometryField)
        ]
        self.geometry_field = self._get_geometry_field()
        default_crs = self.geometry_field.srid  # checks lookup too
        if not self.crs:
            self.crs = CRS.from_string(default_crs)

    @cached_property
    def geometry_field_names(self):
        return [f.name for f in self.geometry_fields]

    @cached_property
    def fields(self) -> List[Tuple[str, str]]:
        """Return all fields that can be queried."""
        fields = []
        for model_field in self.model._meta.get_fields():
            if isinstance(model_field, models.ForeignKey):
                # Don't let it query on the relation value yet
                field_name = model_field.attname
            else:
                field_name = model_field.name

            field_type = self.get_field_type(model_field)
            fields.append((field_name, field_type))

        return fields

    def get_field_type(self, model_field) -> str:
        """Determine the XSD field type for a Django field."""
        if isinstance(model_field, models.ForeignKey):
            # Don't let it query on the relation value yet
            return self.get_field_type(model_field.remote_field)
        elif isinstance(model_field, models.IntegerField):
            return "integer"
        elif model_field.name == self.geometry_field_name:
            return "gml:GeometryPropertyType"
        else:
            return "string"

    def _get_geometry_field(self) -> GeometryField:
        """Access the Django field"""
        if not self.geometry_fields:
            raise ImproperlyConfigured(
                f"Django model {self.model.__name__} does not have to a geometry field."
            ) from None

        if self.geometry_field_name:
            return self.model._meta.get_field(self.geometry_field_name)
        else:
            self.geometry_field_name = self.geometry_fields[0].name
            return self.geometry_fields[0]

    def get_bounding_box(self) -> Optional[BoundingBox]:
        """Returns a WGS84 BoundingBox."""
        if self.geometry_field.srid != WGS84.srid:
            geo_expression = Transform(self.geometry_field.name, WGS84.srid)
        else:
            geo_expression = self.geometry_field.name

        bbox = self.model.objects.aggregate(a=Extent(geo_expression))["a"]
        return BoundingBox(*bbox, crs=WGS84) if bbox else None

    def get_envelope(self, instance, crs: CRS) -> Optional[BoundingBox]:
        """Get the bounding box for a single instance"""
        bbox = BoundingBox(inf, inf, -inf, -inf, crs=crs)

        for model_field in self.geometry_fields:
            geometry = getattr(instance, model_field.name)
            if geometry is not None:
                bbox.extend_to_geometry(geometry)

        return bbox if bbox.lower_lat != inf else None
