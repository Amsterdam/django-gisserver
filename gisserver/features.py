"""Dataclasses that expose the metadata for the GetCapabilities call."""
import html
from functools import reduce

import operator
from dataclasses import dataclass
from typing import List, Optional, Union

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models import Extent, GeometryField
from django.contrib.gis.db.models.functions import Transform
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import cached_property  # py3.8: functools

from gisserver.types import CRS, WGS84, BoundingBox, XsdElement, XsdTypes

NoneType = type(None)


XSD_TYPES = {
    models.CharField: XsdTypes.string,
    models.TextField: XsdTypes.string,
    models.BooleanField: XsdTypes.boolean,
    models.IntegerField: XsdTypes.integer,
    models.AutoField: XsdTypes.integer,  # Only as of Django 3.0 this extends from IntegerField
    models.FloatField: XsdTypes.double,
    models.DecimalField: XsdTypes.decimal,
    models.TimeField: XsdTypes.time,
    models.DateTimeField: XsdTypes.dateTime,  # note: DateTimeField extends DateField!
    models.DateField: XsdTypes.date,
    models.URLField: XsdTypes.anyURI,
    gis_models.PointField: XsdTypes.gmlPointPropertyType,
    gis_models.PolygonField: XsdTypes.gmlSurfacePropertyType,
    gis_models.LineStringField: XsdTypes.gmlCurvePropertyType,
    gis_models.MultiPointField: XsdTypes.gmlMultiPointPropertyType,
    gis_models.MultiPolygonField: XsdTypes.gmlMultiSurfacePropertyType,
    gis_models.MultiLineStringField: XsdTypes.gmlMultiCurvePropertyType,
    # Generic alternatives
    gis_models.GeometryCollectionField: XsdTypes.gmlMultiGeometryPropertyType,
    gis_models.GeometryField: XsdTypes.gmlGeometryPropertyType,
}
DEFAULT_XSD_TYPE = XsdTypes.anyType


@dataclass
class ServiceDescription:
    """Basic metadata for an exposed GIS service."""

    title: str
    abstract: Optional[str] = None
    keywords: Optional[List[str]] = None

    provider_name: Optional[str] = None
    provider_site: Optional[str] = None
    contact_person: Optional[str] = None


class FeatureType:
    """Declare a feature that is exposed on the map.

    All WFS operations use this class to read the feature ype.
    You may subclass this class to provide extensions,
    such as redefining :meth:`get_queryset`.

    This corresponds with a single Django model.
    """

    def __init__(
        self,
        queryset: models.QuerySet,
        fields: Union[str, List[str], NoneType] = None,
        geometry_field_name: str = None,
        name: str = None,
        # WFS Metadata:
        title: str = None,
        abstract: str = None,
        keywords: List[str] = None,
        crs: CRS = None,
        other_crs: List[CRS] = None,
        metadata_url: Optional[str] = None,
    ):
        """
        :param queryset: The queryset to retrieve the data.
        :param fields: Define which fields to show in the WFS data.
        :param geometry_field_name: Name of the geometry field to expose (default = auto detect).
        :param name: Name, also used as XML tag name.
        :param title: Used in WFS metadata.
        :param abstract: Used in WFS metadata.
        :param keywords: Used in WFS metadata.
        :param crs: Used in WFS metadata.
        :param other_crs: Used in WFS metadata.
        :param metadata_url: Used in WFS metadata.
        """
        if isinstance(queryset, models.QuerySet):
            self.queryset = queryset
            self.model = queryset.model
        elif isinstance(queryset, type) and issubclass(queryset, models.Model):
            # In case a model is provided, fix that
            self.model = queryset
            self.queryset = self.model.objects.all()
        else:
            raise TypeError("FeatureType expects a model or queryset")

        self._fields = fields
        self._geometry_field_name = geometry_field_name
        self.name = name or self.model._meta.model_name
        self.title = title or self.model._meta.verbose_name
        self.abstract = abstract
        self.keywords = keywords or []
        self._crs = crs
        self.other_crs = other_crs or []
        self.metadata_url = metadata_url

        # Validate that the name doesn't require XML escaping.
        if html.escape(self.name) != self.name or " " in self.name:
            raise ValueError(f"Invalid feature name for XML: <app:{self.name}>")

        # Auto-detect geometry fields (also fills geometry_field_name)
        self.geometry_fields = [
            f
            for f in self.model._meta.get_fields()
            if isinstance(f, gis_models.GeometryField)
        ]

    def check_permissions(self, request):
        """Hook that allows subclasses to reject access for datasets.
        It may raise a Django PermissionDenied error.
        """
        pass

    @cached_property
    def geometry_field_names(self):
        return {f.name for f in self.geometry_fields}

    @cached_property
    def fields(self) -> List[str]:
        """Define which fields to render."""
        # This lazy reading allows providing 'fields' as lazy value.
        if self._fields is None:
            return [self.geometry_field_name]
        elif isinstance(self._fields, str):
            if self._fields == "__all__":
                return self._get_all_fields()
            else:
                raise TypeError('FeatureType.fields accepts lists and "__all__"')
        else:
            return list(self._fields)

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

    def get_field(self, field_name: str) -> models.Field:
        """Return a single field from the model."""
        return self.model._meta.get_field(field_name)

    def get_field_type(self, model_field: models.Field) -> XsdTypes:
        """Determine the XSD field type for a Django field."""
        try:
            # Direct instance, quickly resolved!
            return XSD_TYPES[model_field.__class__]
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

        if model_field.name in self.geometry_field_names:
            return XsdTypes.gmlGeometryPropertyType
        else:
            # Default XML choice:
            return DEFAULT_XSD_TYPE

    @cached_property
    def geometry_field(self) -> gis_models.GeometryField:
        """Give access to the Django field that holds the geometry."""
        if not self.geometry_fields:
            raise ImproperlyConfigured(
                f"Django model {self.model.__name__} does not have to a geometry field."
            ) from None

        if self.geometry_field_name:
            return self.model._meta.get_field(self.geometry_field_name)
        else:
            return self.geometry_fields[0]

    @cached_property
    def geometry_field_name(self) -> str:
        if self._geometry_field_name:
            return self._geometry_field_name
        else:
            if not self.geometry_fields:
                raise ImproperlyConfigured(
                    f"Django model {self.model.__name__} does not have to a geometry field."
                ) from None
            return self.geometry_fields[0].name

    @cached_property
    def crs(self) -> CRS:
        """Tell which projection the data should be presented at."""
        if self._crs is None:
            # Default CRS
            return CRS.from_srid(self.geometry_field.srid)  # checks lookup too
        else:
            return self._crs

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

        bbox = self.get_queryset().aggregate(a=Extent(geo_expression))["a"]
        return BoundingBox(*bbox, crs=WGS84) if bbox else None

    def get_envelope(self, instance, crs: CRS) -> Optional[BoundingBox]:
        """Get the bounding box for a single instance"""
        geometries = [
            geom
            for geom in (getattr(instance, f.name) for f in self.geometry_fields)
            if geom is not None
        ]
        if not geometries:
            return None

        # Perform the combining of geometries inside libgeos
        geometry = (
            geometries[0] if len(geometries) == 1 else reduce(operator.or_, geometries)
        )
        if geometry.srid != crs.srid:
            crs.apply_to(geometry)  # avoid clone
        return BoundingBox.from_geometry(geometry, crs=crs)

    @cached_property
    def xsd_fields(self) -> List[XsdElement]:
        """Return the definition of this feature as a list of XSD elements."""
        return [self.get_xsd_field(name) for name in self.fields]

    def get_xsd_field(self, name):
        """Define the XMLSchema definition for a model field.
        This is used in DescribeFeatureType.
        """
        field = self.get_field(name)
        return XsdElement(
            name=name,
            type=self.get_field_type(field),
            nillable=field.null,
            min_occurs=0,
            max_occurs=1 if isinstance(field, GeometryField) else None,
            source=field,
        )
