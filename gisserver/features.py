"""Dataclasses that expose the metadata for the GetCapabilities call."""
import html
import operator
from dataclasses import dataclass
from functools import lru_cache, reduce
from typing import List, Optional, Type, Union

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models import Extent, GeometryField
from django.contrib.gis.db.models.functions import Transform
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import cached_property  # py3.8: functools

from gisserver.types import (
    XsdAnyType,
    XsdComplexType,
    XsdElement,
    XsdTypes,
)
from gisserver.geometries import BoundingBox, CRS, WGS84

try:
    from typing import Literal  # Python 3.8

    _all_ = Literal["__all__"]
except ImportError:
    _all_ = str


__all__ = [
    "FeatureType",
    "field",
    "FeatureField",
    "ComplexFeatureField",
]

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


def _get_basic_field_type(field_name: str, model_field: models.Field) -> XsdAnyType:
    """Determine the XSD field type for a Django field."""
    try:
        # Direct instance, quickly resolved!
        return XSD_TYPES[model_field.__class__]
    except KeyError:
        pass

    if isinstance(model_field, models.ForeignKey):
        # Don't let it query on the relation value yet
        return _get_basic_field_type(field_name, model_field.target_field)
    elif isinstance(model_field, ForeignObjectRel):
        # e.g. ManyToOneRel descriptor of a foreignkey_id field.
        return _get_basic_field_type(field_name, model_field.remote_field.target_field)
    else:
        # Subclass checks:
        for field_cls, xsd_type in XSD_TYPES.items():
            if isinstance(model_field, field_cls):
                return xsd_type

    # Default:
    if isinstance(model_field, GeometryField):
        return XsdTypes.gmlGeometryPropertyType
    else:
        # Default XML choice:
        return DEFAULT_XSD_TYPE


def _get_model_fields(model, fields):
    if fields == "__all__":
        # All regular fields
        return [
            FeatureField(
                name=f.attname if isinstance(f, models.ForeignKey) else f.name,
                model=model,
            )
            for f in model._meta.get_fields()
        ]
    else:
        # Only defined fields
        fields = [f if isinstance(f, FeatureField) else FeatureField(f) for f in fields]
        for field in fields:
            field.bind(model)
        return fields


@dataclass
class ServiceDescription:
    """Basic metadata for an exposed GIS service."""

    title: str
    abstract: Optional[str] = None
    keywords: Optional[List[str]] = None

    provider_name: Optional[str] = None
    provider_site: Optional[str] = None
    contact_person: Optional[str] = None


class FeatureField:
    """The configuration for an field inside a WFS Feature.

    This defines how a Django model field is mapped into
    an XSD definition that the remaining application uses.
    """

    model: Optional[Type[models.Model]]
    model_field: Optional[models.Field]

    def __init__(self, name, model=None):
        self.name = name
        self.model = None
        self.model_field = None
        if model is not None:
            self.bind(model)

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"

    def _get_xsd_type(self):
        return _get_basic_field_type(self.name, self.model_field)

    def bind(self, model: Type[models.Model]):
        """Late-binding for the model"""
        if self.model is not None:
            raise RuntimeError(f"Feature field '{self.name}' cannot be reused")
        self.model = model
        self.model_field = self.model._meta.get_field(self.name)

    @cached_property
    def xsd_element(self) -> XsdElement:
        """Define the XMLSchema definition for a model field.
        This is used in DescribeFeatureType.
        """
        return XsdElement(
            name=self.name,
            type=self._get_xsd_type(),
            nillable=self.model_field.null,
            min_occurs=0,
            max_occurs=1 if isinstance(self.model_field, GeometryField) else None,
            source=self.model_field,
        )


_FieldDefinition = Union[str, FeatureField]
_FieldDefinitions = Union[_all_, List[_FieldDefinition]]


class ComplexFeatureField(FeatureField):
    """The configuration for an embedded foreign-key field.

    This translates the foreign key into an embedded XSD complex type.
    """

    def __init__(self, name: str, fields: _FieldDefinitions):
        """
        :param name: Name of the model field.
        :param fields: List of fields to expose for the target model. This can
            be a list of :class:`FeatureField` objects, or plain field names.
            Using ``__all__`` also works but is not recommended outside testing.
        """
        super().__init__(name)
        self._fields = fields

    def _get_xsd_type(self) -> XsdComplexType:
        """Generate the XSD description for the field with an object relation."""
        fields = _get_model_fields(self.target_model, self._fields)
        return XsdComplexType(
            name=f"{self.target_model._meta.object_name}Type",
            elements=[field.xsd_element for field in fields],
            source=self.target_model,
        )

    @property
    def target_model(self):
        """Detect which model the relation points to."""
        if self.model_field is None:
            raise RuntimeError("FeatureField.bind() is not called yet")

        if isinstance(self.model_field, models.ForeignKey):
            return self.model_field.target_field.model
        elif isinstance(self.model_field, ForeignObjectRel):
            # e.g. ManyToOneRel descriptor of a foreignkey_id field.
            return self.model_field.remote_field.model
        else:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not support fields of "
                f"type {self.model_field.__class__.__name__}."
            )


def field(name: str, fields: Optional[_FieldDefinitions] = None) -> FeatureField:
    """Shortcut to define a WFS field.

    This automatically selects the proper field class,
    so little knowledge is needed about the internal working.

    :param name: Name of the model field.
    :param fields: If the field exposes a foreign key, provide it's child element names.
        This can be a list of :func:`field` elements, or plain field names.
        Using ``__all__`` also works but is not recommended outside testing.
    """
    if fields is not None:
        return ComplexFeatureField(name=name, fields=fields)
    else:
        return FeatureField(name)


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
        *,
        fields: Optional[_FieldDefinitions] = None,
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
            This can be a list of field names, or :class:`FeatureField` objects.
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
        self._cached_resolver = None

    def check_permissions(self, request):
        """Hook that allows subclasses to reject access for datasets.
        It may raise a Django PermissionDenied error.
        """
        pass

    @cached_property
    def geometry_field_names(self):
        return {f.name for f in self.geometry_fields}

    @cached_property
    def fields(self) -> List[FeatureField]:
        """Define which fields to render."""
        # This lazy reading allows providing 'fields' as lazy value.
        if self._fields is None:
            return [FeatureField(self.geometry_field_name, self.model)]
        else:
            return _get_model_fields(self.model, self._fields)

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
    def xsd_type(self) -> XsdComplexType:
        """Return the definition of this feature as an XSD Complex Type."""
        return XsdComplexType(
            name=f"{self.name.title()}Type",
            elements=[field.xsd_element for field in self.fields],
            source=self.model,
        )

    def resolve_element(self, xpath: str) -> Optional[XsdElement]:
        """Resolve the element, only returns the final node."""
        return self.resolve_element_path(xpath)[-1]

    def resolve_element_path(self, xpath: str) -> Optional[List[XsdElement]]:
        """Resolve the element, and return the whole path.
        This method is wrapped inside an lru_cache.
        """
        if self._cached_resolver is None:
            self._cached_resolver = lru_cache(100)(self.xsd_type.resolve_element_path)

        path = self._cached_resolver(xpath)
        if path is None:
            raise ValueError(f"Field '{xpath}' does not exist.")

        return path
