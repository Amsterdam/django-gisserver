"""Dataclasses that expose the metadata for the GetCapabilities call."""
from dataclasses import dataclass, field
from math import inf
from typing import List, Optional, Union

from django.contrib.gis.db.models import Extent, GeometryField
from django.contrib.gis.db.models.functions import Transform
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import cached_property  # py3.8: functools

from gisserver.types import CRS, WGS84, BoundingBox, XsdTypes

NoneType = type(None)


XSD_TYPES = {
    models.BooleanField: XsdTypes.boolean,
    models.IntegerField: XsdTypes.integer,
    models.FloatField: XsdTypes.double,
    models.DecimalField: XsdTypes.decimal,
    models.TimeField: XsdTypes.time,
    models.DateField: XsdTypes.date,
    models.DateTimeField: XsdTypes.dateTime,
    models.URLField: XsdTypes.anyURI,
}


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

    #: The queryset to retrieve the data.
    queryset: models.QuerySet

    #: Define which fields to show in the WFS data:
    fields: Union[str, List[str], NoneType] = None

    #: Name of the geometry field to expose (default = auto detect)
    geometry_field_name: str = None

    #: Name, also used as XML tag name
    name: str = None

    # WFS Metadata:
    title: str = None
    abstract: str = None
    keywords: List[str] = field(default_factory=list)
    crs: CRS = None
    other_crs: List[CRS] = field(default_factory=list)
    metadata_url: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.queryset, models.QuerySet):
            self.model = self.queryset.model
        elif isinstance(self.queryset, type) and issubclass(
            self.queryset, models.Model
        ):
            # In case a model is provided, fix that
            self.model = self.queryset
            self.queryset = self.model.objects.all()
        else:
            raise TypeError("FeatureType expects a model or queryset")

        # Add some defaults
        if not self.name:
            self.name = self.model._meta.model_name
        if not self.title:
            self.title = self.model._meta.verbose_name

        # Auto-detect geometry fields (also fills geometry_field_name)
        self.geometry_fields = [
            f for f in self.model._meta.get_fields() if isinstance(f, GeometryField)
        ]
        self.geometry_field = self._get_geometry_field()

        if self.fields is None:
            self.fields = [self.geometry_field_name]
        elif isinstance(self.fields, str):
            if self.fields == "__all__":
                self.fields = self._get_all_fields()
            else:
                raise TypeError('FeatureType.fields accepts lists and "__all__"')

        # Default CRS
        default_crs = self.geometry_field.srid  # checks lookup too
        if not self.crs:
            self.crs = CRS.from_string(default_crs)

    @cached_property
    def geometry_field_names(self):
        return [f.name for f in self.geometry_fields]

    @cached_property
    def fields_with_type(self):
        fields = []
        for name in self.fields:
            field = self.model._meta.get_field(name)
            fields.append((name, self.get_field_type(field)))

        return fields

    def _get_all_fields(self) -> List[str]:
        """Return all fields that can be queried."""
        fields = []
        for model_field in self.model._meta.get_fields():
            if isinstance(model_field, models.ForeignKey):
                # Don't let it query on the relation value yet
                field_name = model_field.attname
            else:
                field_name = model_field.name

            fields.append(field_name)

        return fields

    def get_field_type(self, model_field: models.Field) -> XsdTypes:
        """Determine the XSD field type for a Django field."""
        try:
            # Direct instance, quickly resolved!
            return XSD_TYPES[model_field]
        except KeyError:
            pass

        if isinstance(model_field, models.ForeignKey):
            # Don't let it query on the relation value yet
            return self.get_field_type(model_field.target_field)
        elif isinstance(model_field, ForeignObjectRel):
            # e.g. ManyToOneRel descriptor of a foreignkey_id field.
            return self.get_field_type(model_field.remote_field.target_field)
        elif model_field.name == self.geometry_field_name:
            return XsdTypes.gmlGeometryPropertyType
        else:
            # Subclass checks:
            for field_cls, xsd_type in XSD_TYPES.items():
                if isinstance(model_field, field_cls):
                    return xsd_type

        # Default XML choice:
        return XsdTypes.string

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

    def get_queryset(self) -> models.QuerySet:
        """Return the queryset that is used as basis for this feature."""
        # Adding .all() to avoid filling the caches.
        return self.queryset.all()

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
