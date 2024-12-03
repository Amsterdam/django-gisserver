"""The configuration of a "feature type" in the WFS server.

The "feature type" definitions define what models and attributes are exposed in the WFS server.
When a model attribute is mentioned in the feature type, it can be exposed and queried against.
Any field that is not mentioned in a definition, will therefore not be available, nor queryable.
This metadata is used in the ``GetCapabilities`` call to advertise all available feature types.

To handle other WFS request types besides ``GetCapabilities``, the "feature type" definition
is translated internally into an internal XML Schema Definition (:mod:`gisserver.types`).
That schema maps all model attributes to a specific XML layout, and includes
all XSD Complex Types, elements and attributes linked to the Django model metadata.
The feature type classes (and field types) offer a flexible translation
from attribute listings into a schema definition.
For example, model relationships can be modelled to a different XML layout.
"""

from __future__ import annotations

import html
import operator
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property, lru_cache, reduce
from typing import Union

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models import Extent, GeometryField
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models
from django.db.models.fields.related import ForeignObjectRel  # Django 2.2 import

from gisserver.db import conditional_transform
from gisserver.exceptions import ExternalValueError
from gisserver.geometries import CRS, WGS84, BoundingBox
from gisserver.types import (
    GmlBoundedByElement,
    GmlIdAttribute,
    GmlNameElement,
    XPathMatch,
    XsdAnyType,
    XsdComplexType,
    XsdElement,
    XsdTypes,
)

if "django.contrib.postgres" in settings.INSTALLED_APPS:
    from django.contrib.postgres.fields import ArrayField
else:
    ArrayField = None

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
    "get_basic_field_type",
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


def get_basic_field_type(
    field_name: str, model_field: models.Field | ForeignObjectRel
) -> XsdAnyType:
    """Determine the XSD field type for a Django field."""
    if ArrayField is not None and isinstance(model_field, ArrayField):
        # Determine the type based on the contents.
        # The array notation is written as "is_many"
        model_field = model_field.base_field

    try:
        # Direct instance, quickly resolved!
        return XSD_TYPES[model_field.__class__]
    except KeyError:
        pass

    if isinstance(model_field, models.ForeignKey):
        # Don't let it query on the relation value yet
        return get_basic_field_type(field_name, model_field.target_field)
    elif isinstance(model_field, ForeignObjectRel):
        # e.g. ManyToOneRel descriptor of a foreignkey_id field.
        return get_basic_field_type(field_name, model_field.remote_field.target_field)
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


def _get_model_fields(
    model: type[models.Model],
    fields: _all_ | list[str],
    parent: ComplexFeatureField | None = None,
    feature_type: FeatureType | None = None,
):
    if fields == "__all__":
        # All regular fields
        # Relationships will not be expanded since it can expose so many other fields.
        # Only the relationships that store an ID on the model itself will be exposed.
        return [
            FeatureField(
                name=f.attname,  # using attname so foreignkeys use the name_id field.
                # .bind() is called directly by providing these arguments via init:
                model=model,
                parent=parent,
                feature_type=feature_type,
            )
            for f in model._meta.get_fields()
            if not f.is_relation or f.many_to_one or f.one_to_one  # ForeignKey  # OneToOneField
        ]
    else:
        # Only defined fields
        fields = [f if isinstance(f, FeatureField) else FeatureField(f) for f in fields]
        for field in fields:
            field.bind(model, parent=parent, feature_type=feature_type)
        return fields


@dataclass
class ServiceDescription:
    """Basic metadata for an exposed GIS service."""

    title: str
    abstract: str | None = None
    keywords: list[str] | None = None

    provider_name: str | None = None
    provider_site: str | None = None
    contact_person: str | None = None


class FeatureField:
    """The configuration for a field inside a WFS Feature.

    This defines how a Django model field is mapped into
    an XSD definition that the remaining application uses.
    """

    #: Allow to override the XSD element type that this field will generate.
    xsd_element_class: type[XsdElement] = XsdElement

    model: type[models.Model] | None
    model_field: models.Field | ForeignObjectRel | None

    def __init__(
        self,
        name,
        model_attribute=None,
        model=None,
        parent: ComplexFeatureField | None = None,
        feature_type: FeatureType | None = None,
        abstract=None,
        xsd_class: type[XsdElement] | None = None,
    ):
        self.name = name
        self.model_attribute = model_attribute
        self.model = None
        self.model_field = None
        self.parent = parent
        self.feature_type = feature_type
        self.abstract = abstract

        # Allow to override the class attribute on 'self',
        # which avoids having to subclass this field class as well.
        if xsd_class is not None:
            self.xsd_element_class = xsd_class

        self._nillable_relation = False
        if model is not None:
            self.bind(model, parent=parent, feature_type=feature_type)

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"

    def _get_xsd_type(self):
        return get_basic_field_type(self.name, self.model_field)

    def bind(
        self,
        model: type[models.Model],
        parent: ComplexFeatureField | None = None,
        feature_type: FeatureType | None = None,
    ):
        """Late-binding for the model.

        This resolves the model field object from the provided model.
        This method is called internally when the field definition wasn't
        linked to a model yet. This allows the fields to be defined first,
        in external code, and then become part of the ``FeatureType`` fields
        list.

        :param model: The model is field is linked to.
        :param parent: When this element is part of a complex feature,
                       this links to the parent field.
        :param feature_type: The original feature type that his element was mentioned in.
        """
        if self.model is not None:
            raise RuntimeError(f"Feature field '{self.name}' cannot be reused")
        self.model = model
        self.parent = parent
        self.feature_type = feature_type

        if self.model_attribute:
            # Support dot based field traversal.
            field_path = self.model_attribute.split(".")
            try:
                field: models.Field = self.model._meta.get_field(field_path[0])
            except FieldDoesNotExist as e:
                raise ImproperlyConfigured(
                    f"FeatureField '{self.name}' has an invalid"
                    f" model_attribute: '{self.model_attribute}' can't be"
                    f" resolved for model '{self.model.__name__}'."
                ) from e

            for name in field_path[1:]:
                if field.null:
                    self._nillable_relation = True

                if not field.is_relation:
                    # Note this tests the previous loop variable, so it checks whether the
                    # field can be walked into in order to resolve the next dotted name below.
                    raise ImproperlyConfigured(
                        f"FeatureField '{field.name}' has an invalid model_attribute: "
                        f"field '{name}' is a '{field.__class__.__name__}', not a relation."
                    )

                field = field.related_model._meta.get_field(name)
            self.model_field = field
        else:
            self.model_field = self.model._meta.get_field(self.name)

    @cached_property
    def xsd_element(self) -> XsdElement:
        """Define the XMLSchema definition for a model field.

        This definition is used by the remaining application to access the
        data. It's the basis for DescribeFeatureType, and it's ``get_value()``
        method is read to access the model field data.
        """
        if self.model_field is None:
            raise RuntimeError(f"bind() was not called for {self!r}")

        # Determine max number of occurrences.
        if isinstance(self.model_field, GeometryField):
            max_occurs = 1  # be explicit here, like mapserver does.
        elif self.model_field.many_to_many or self.model_field.one_to_many:
            max_occurs = "unbounded"  # M2M or reverse FK field
        elif ArrayField is not None and isinstance(self.model_field, ArrayField):
            max_occurs = self.model_field.size or "unbounded"
        else:
            max_occurs = None  # default is 1, but attribute can be left out.

        return self.xsd_element_class(
            name=self.name,
            type=self._get_xsd_type(),
            nillable=self.model_field.null or self._nillable_relation,
            min_occurs=0,
            max_occurs=max_occurs,
            model_attribute=self.model_attribute,
            source=self.model_field,
            feature_type=self.feature_type,
        )


_FieldDefinition = Union[str, FeatureField]
_FieldDefinitions = Union[_all_, list[_FieldDefinition]]


class ComplexFeatureField(FeatureField):
    """The configuration for an embedded relation field.

    This field type is suitable for any relational object, including
    foreign keys, reverse relations and M2M fields. The internal logic
    translates the relation into an embedded XSD complex type.
    """

    def __init__(
        self,
        name: str,
        fields: _FieldDefinitions,
        model_attribute=None,
        model=None,
        abstract=None,
        xsd_class=None,
        xsd_base_type=XsdTypes.gmlAbstractFeatureType,
    ):
        """
        :param name: Name of the model field.
        :param fields: List of fields to expose for the target model. This can
            be a list of :class:`FeatureField` objects, or plain field names.
            Using ``__all__`` also works but is not recommended outside testing.
        """
        super().__init__(
            name,
            model_attribute=model_attribute,
            model=model,
            abstract=abstract,
            xsd_class=xsd_class,
        )
        self.xsd_base_type = xsd_base_type
        self._fields = fields

    @cached_property
    def fields(self) -> list[FeatureField]:
        """Provide all fields that will be rendered as part of this complex field."""
        return _get_model_fields(self.target_model, self._fields, parent=self)

    def _get_xsd_type(self) -> XsdComplexType:
        """Generate the XSD description for the field with an object relation."""
        pk_field = self.target_model._meta.pk

        return XsdComplexType(
            name=f"{self.target_model._meta.object_name}Type",
            elements=[field.xsd_element for field in self.fields],
            attributes=[
                # Add gml:id attribute definition, so it can be resolved in xpath
                GmlIdAttribute(
                    type_name=self.name,
                    source=pk_field,
                    model_attribute=pk_field.name,
                    feature_type=self.feature_type,
                )
            ],
            base=self.xsd_base_type,
            source=self.target_model,
        )

    @property
    def target_model(self) -> type[models.Model]:
        """Detect which model the relation points to."""
        if self.model_field is None:
            raise RuntimeError("FeatureField.bind() is not called yet")
        elif not self.model_field.is_relation:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not support fields of "
                f"type {self.model_field.__class__.__name__}."
            )
        else:
            return self.model_field.related_model


def field(
    name: str,
    *,
    model_attribute=None,
    abstract: str | None = None,
    fields: _FieldDefinitions | None = None,
    xsd_class: type[XsdElement] | None = None,
) -> FeatureField:
    """Shortcut to define a WFS field.

    This automatically selects the proper field class,
    so little knowledge is needed about the internal working.

    :param name: Name of the model field.
    :param fields: If the field exposes a foreign key, provide it's child element names.
        This can be a list of :func:`field` elements, or plain field names.
        Using ``__all__`` also works but is not recommended outside testing.
    """
    if fields is not None:
        return ComplexFeatureField(
            name=name,
            model_attribute=model_attribute,
            fields=fields,
            abstract=abstract,
            xsd_class=xsd_class,
        )
    else:
        return FeatureField(
            name,
            model_attribute=model_attribute,
            abstract=abstract,
            xsd_class=xsd_class,
        )


@dataclass
class FeatureRelation:
    """Tell which related fields are queried by the feature.
    Each dict holds an ORM-path, with the relevant sub-elements.
    """

    #: The ORM path that is queried for this particular relation
    orm_path: str
    #: The fields that will be retrieved for that path
    orm_fields: set[str]
    #: The model that is accessed for this relation (if set)
    related_model: type[models.Model] | None
    #: The source elements that access this relation.
    xsd_elements: list[XsdElement]

    @cached_property
    def _local_model_field_names(self) -> list[str]:
        """Tell which local fields of the model will be accessed by this feature."""

        meta = self.related_model._meta
        result = []
        for name in self.orm_fields:
            model_field = meta.get_field(name)
            if not model_field.many_to_many and not model_field.one_to_many:
                result.append(name)

        # When this relation is retrieved through a ManyToOneRel (reverse FK),
        # the prefetch_related() also needs to have the original foreign key
        # in order to link all prefetches to the proper parent instance.
        for xsd_element in self.xsd_elements:
            if xsd_element.source is not None and xsd_element.source.one_to_many:
                result.append(xsd_element.source.field.name)

        return result


class FeatureType:
    """Declare a feature that is exposed on the map.

    All WFS operations use this class to read the feature ype.
    You may subclass this class to provide extensions,
    such as redefining :meth:`get_queryset`.

    This corresponds with a single Django model.
    """

    #: Allow to override the XSD complex type that this feature will generate.
    xsd_type_class: type[XsdComplexType] = XsdComplexType

    def __init__(
        self,
        queryset: models.QuerySet,
        *,
        fields: _FieldDefinitions | None = None,
        display_field_name: str | None = None,
        geometry_field_name: str | None = None,
        name: str | None = None,
        # WFS Metadata:
        title: str | None = None,
        abstract: str | None = None,
        keywords: list[str] | None = None,
        crs: CRS | None = None,
        other_crs: list[CRS] | None = None,
        metadata_url: str | None = None,
        # Settings
        show_name_field: bool = True,
        xml_prefix: str = "app",
    ):
        """
        :param queryset: The queryset to retrieve the data.
        :param fields: Define which fields to show in the WFS data.
            This can be a list of field names, or :class:`FeatureField` objects.
        :param display_field_name: Name of the field that's used as general string representation.
        :param geometry_field: Name of the geometry field to expose (default = auto detect).
        :param name: Name, also used as XML tag name.
        :param title: Used in WFS metadata.
        :param abstract: Used in WFS metadata.
        :param keywords: Used in WFS metadata.
        :param crs: Used in WFS metadata.
        :param other_crs: Used in WFS metadata.
        :param metadata_url: Used in WFS metadata.
        :param show_name_field: Whether to show the ``gml:name`` or the GeoJSON ``geometry_name``
            field. Default is to show a field when ``name_field`` is given.
        :param xml_prefix: The XML namespace prefix to use.
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
        self.display_field_name = display_field_name
        self._geometry_field_name = geometry_field_name
        self.name = name or self.model._meta.model_name
        self.title = title or self.model._meta.verbose_name
        self.abstract = abstract
        self.keywords = keywords or []
        self._crs = crs
        self.other_crs = other_crs or []
        self.metadata_url = metadata_url

        # Settings
        self.show_name_field = show_name_field
        self.xml_prefix = xml_prefix

        # Validate that the name doesn't require XML escaping.
        if html.escape(self.name) != self.name or " " in self.name or ":" in self.name:
            raise ValueError(f"Invalid feature name for XML: <{self.xml_name}>")

        self._cached_resolver = lru_cache(100)(self._inner_resolve_element)

    def check_permissions(self, request):
        """Hook that allows subclasses to reject access for datasets.
        It may raise a Django PermissionDenied error.
        """

    @cached_property
    def xml_name(self):
        """Return the feature name with xml namespace prefix."""
        return f"{self.xml_prefix}:{self.name}"

    @cached_property
    def supported_crs(self) -> list[CRS]:
        """Return all spatial reference system ID's that this feature supports."""
        return [self.crs] + self.other_crs

    @cached_property
    def geometry_fields(self) -> list[GeometryField]:
        """Tell which fields of the model have a geometry field.
        This only compares against fields that are mentioned in this feature type.
        """
        return [
            ff.model_field or getattr(self.model, ff.model_attribute)
            for ff in self.fields
            if ff.xsd_element.is_geometry
        ]

    @cached_property
    def orm_relations(self) -> list[FeatureRelation]:
        """Tell which fields will be retrieved from related fields.

        This gives an object layout based on the XSD elements,
        that can be used for prefetching data.
        """
        models = {}
        fields = defaultdict(set)
        elements = defaultdict(list)

        # Check all elements that render as "dotted" flattened relation
        for xsd_element in self.xsd_type.flattened_elements:
            if xsd_element.source is not None:
                # Split "relation.field" notation into path, and take the field as child attribute.
                obj_path, field = xsd_element.orm_relation
                elements[obj_path].append(xsd_element)
                fields[obj_path].add(field)
                # field is already on relation:
                models[obj_path] = xsd_element.source.model

        # Check all elements that render as "nested" complex type:
        for xsd_element in self.xsd_type.complex_elements:
            # The complex element itself points to the root of the path,
            # all sub elements become the child attributes.
            obj_path = xsd_element.orm_path
            elements[obj_path].append(xsd_element)
            fields[obj_path] = {
                f.orm_path
                for f in xsd_element.type.elements
                if not f.is_many or f.is_array  # exclude M2M, but include ArrayField
            }
            if xsd_element.source:
                # field references a related object:
                models[obj_path] = xsd_element.source.related_model

        return [
            FeatureRelation(
                orm_path=obj_path,
                orm_fields=sub_fields,
                related_model=models.get(obj_path),
                xsd_elements=elements[obj_path],
            )
            for obj_path, sub_fields in fields.items()
        ]

    @cached_property
    def _local_model_field_names(self) -> list[str]:
        """Tell which local fields of the model will be accessed by this feature."""
        return [
            (ff.model_field.name if ff.model_field else ff.model_attribute)
            for ff in self.fields
            if not ff.model_field.many_to_many
            and not ff.model_field.one_to_many
            and not (ff.model_attribute and "." in ff.model_attribute)
        ]

    @cached_property
    def fields(self) -> list[FeatureField]:
        """Define which fields to render."""
        # This lazy reading allows providing 'fields' as lazy value.
        if self._fields is None:
            # Autoconfig, no fields defined.
            if not self._geometry_field_name:
                self._geometry_field_name = next(
                    f.name
                    for f in self.model._meta.get_fields()
                    if isinstance(f, gis_models.GeometryField)
                )

            return [FeatureField(self._geometry_field_name, model=self.model, feature_type=self)]
        else:
            return _get_model_fields(self.model, self._fields, feature_type=self)

    @cached_property
    def display_field(self) -> models.Field | None:
        """Give access to the field that holds the string-representation."""
        if not self.show_name_field or not self.display_field_name:
            return None
        else:
            return self.model._meta.get_field(self.display_field_name)

    @cached_property
    def geometry_field(self) -> gis_models.GeometryField:
        """Give access to the Django field that holds the geometry."""
        if not self.geometry_fields:
            raise ImproperlyConfigured(
                f"FeatureType '{self.name}' does not expose a geometry field."
            ) from None

        if self._geometry_field_name:
            # Explicitly mentioned, use that field.
            # Check whether the server is not accidentally exposing another field
            # that is not part of the type definition.
            field = next(
                (
                    field
                    for field in self.geometry_fields
                    if field.name == self._geometry_field_name
                ),
                None,
            )
            if field is None:
                raise ImproperlyConfigured(
                    f"FeatureType '{self.name}' does not expose the geometry field "
                    f"'{self._geometry_field_name}' as part of its definition."
                )

            return field
        else:
            # Default: take the first geometry
            return self.geometry_fields[0]

    @cached_property
    def geometry_field_name(self) -> str:
        """Tell which field is the geometry field."""
        # Due to internal reorganization this property is no longer needed,
        # retained for backward compatibility and to reflect any used input parameters.
        return self.geometry_field.name

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
        # Return a queryset that only retrieves the fields that are actually displayed.
        # That that without .only(), use at least `self.queryset.all()` so a clone is returned.
        return self.queryset.only(*self._local_model_field_names)

    def get_related_queryset(self, feature_relation: FeatureRelation) -> models.QuerySet:
        """Return the queryset that is used for prefetching related data."""
        if feature_relation.related_model is None:
            raise RuntimeError(
                f"Unable to create prefetch queryset for relation {feature_relation.orm_path}, "
                f"source model is not defined for: {feature_relation.xsd_elements!r}"
            )
        # Return a queryset that only retrieves the fields that are displayed.
        return self.filter_related_queryset(
            feature_relation.related_model.objects.only(*feature_relation._local_model_field_names)
        )

    def filter_related_queryset(self, queryset: models.QuerySet) -> models.QuerySet:
        """When a related object returns a queryset, this hook allows extra filtering."""
        return queryset

    def get_bounding_box(self) -> BoundingBox | None:
        """Returns a WGS84 BoundingBox for the complete feature.

        This is used by the GetCapabilities request. It may return ``None``
        when the database table is empty, or the custom queryset doesn't
        return any results.
        """
        if not self.geometry_fields:
            return None

        geo_expression = conditional_transform(
            self.geometry_field.name, self.geometry_field.srid, WGS84.srid
        )

        bbox = self.get_queryset().aggregate(a=Extent(geo_expression))["a"]
        return BoundingBox(*bbox, crs=WGS84) if bbox else None

    def get_envelope(self, instance, crs: CRS | None = None) -> BoundingBox | None:
        """Get the bounding box for a single instance.

        This is only used for native Python rendering. When the database
        rendering is enabled (GISSERVER_USE_DB_RENDERING=True), the calculation
        is entirely performed within the query.
        """
        geometries = [
            geom
            for geom in (getattr(instance, f.name) for f in self.geometry_fields)
            if geom is not None
        ]
        if not geometries:
            return None

        # Perform the combining of geometries inside libgeos
        geometry = geometries[0] if len(geometries) == 1 else reduce(operator.or_, geometries)
        if crs is not None and geometry.srid != crs.srid:
            crs.apply_to(geometry)  # avoid clone
        return BoundingBox.from_geometry(geometry, crs=crs)

    def get_display_value(self, instance: models.Model) -> str:
        """Generate the display name value"""
        if self.display_field_name:
            return getattr(instance, self.display_field_name)
        else:
            return str(instance)

    @property
    def xsd_base_type(self) -> XsdAnyType:
        """Return the base class for the :attr:`xsd_type`.

        This builds an XsdComplexType element that represents
        the contents of :attr:`XsdTypes.gmlAbstractFeatureType`.
        By providing this as Complex Type, the filters can also resolve the
        attributes of ``@gml:id``, ``<gml:name>`` and ``<gml:boundedBy>`` nodes.
        """
        pk_field = self.model._meta.pk

        # Define <gml:boundedBy>, if the feature has a geometry
        base_elements = []
        if self.geometry_fields:
            # Without a geometry, boundaries are not possible.
            base_elements.append(GmlBoundedByElement(feature_type=self))

        if self.show_name_field:
            # Add <gml:name>
            gml_name = GmlNameElement(
                model_attribute=self.display_field_name,
                source=self.display_field,
                feature_type=self,
            )
            base_elements.insert(0, gml_name)

        return XsdComplexType(
            prefix="gml",
            name="AbstractFeatureType",
            elements=base_elements,
            attributes=[
                # Add gml:id attribute definition so it can be resolved in xpath
                GmlIdAttribute(
                    type_name=self.name,
                    source=pk_field,
                    model_attribute=pk_field.name,
                    feature_type=self,
                )
            ],
            base=XsdTypes.gmlAbstractGMLType,
        )

    @cached_property
    def xsd_type(self) -> XsdComplexType:
        """Return the definition of this feature as an XSD Complex Type."""
        return self.xsd_type_class(
            name=f"{self.name.title()}Type",
            elements=[field.xsd_element for field in self.fields],
            base=self.xsd_base_type,
            source=self.model,
        )

    def resolve_element(self, xpath: str) -> XPathMatch:
        """Resolve the element, and the matching object.

        This is used to convert XPath references in requests
        to the actual elements and model attributes for queries.

        Internally, this method caches results.
        """
        nodes = self._cached_resolver(xpath)  # calls _inner_resolve_element
        if nodes is None:
            raise ExternalValueError(f"Field '{xpath}' does not exist.")

        return XPathMatch(self, nodes, query=xpath)

    def _inner_resolve_element(self, xpath: str):
        """Inner part of resolve_element() that is cached.
        This performs any additional checks that happen at the root-level only.
        """
        # Avoid complex XPath features for now. Only element/child works.
        # The attribute selector is not fully implemented, but tested elsewhere.
        if "//" in xpath:
            raise NotImplementedError(
                f"XPath selectors with deeper descendant selectors are not supported: {xpath}"
            )
        elif "::" in xpath:
            raise NotImplementedError(
                f"XPath selectors with expanded syntax are not supported: {xpath}"
            )
        elif "(" in xpath:
            raise NotImplementedError(f"XPath selectors with functions are not supported: {xpath}")

        # Allow /app:ElementName/.. as "absolute" path.
        # Given our internal resolver logic, simple solution is to strip it.
        for root_prefix in (
            f"{self.name}/",
            f"/{self.name}/",
            f"{self.xml_name}/",
            f"/{self.xml_name}/",
        ):
            if xpath.startswith(root_prefix):
                xpath = xpath[len(root_prefix) :]
                break

        return self.xsd_type.resolve_element_path(xpath)
