"""The main configuration for exposing model data in the WFS server.

The "feature type" definitions define what models and attributes are exposed in the WFS server.
When a model attribute is mentioned in the feature type, it can be exposed and queried against.
Any field that is not mentioned in a definition, will therefore not be available, nor queryable.
This metadata is used in the ``GetCapabilities`` call to advertise all available feature types.

The "feature type" definitions ares translated internally into
an internal XML Schema Definition (made from :mod:`gisserver.types`).
That schema maps all model attributes to a specific XML layout, and includes
all XSD Complex Types, elements and attributes linked to the Django model metadata.

The feature type classes (and field types) offer a flexible translation
from attribute listings into a schema definition.
For example, model relationships can be modelled to a different XML layout.
"""

from __future__ import annotations

import html
import itertools
import logging
from dataclasses import dataclass
from functools import cached_property, lru_cache
from typing import TYPE_CHECKING, Literal

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models import GeometryField
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models
from django.http import HttpRequest

from gisserver import conf
from gisserver.compat import ArrayField, GeneratedField
from gisserver.crs import CRS
from gisserver.db import get_wgs84_bounding_box
from gisserver.exceptions import ExternalValueError, InvalidParameterValue
from gisserver.geometries import WGS84BoundingBox
from gisserver.parsers.xml import parse_qname, xmlns
from gisserver.types import (
    GeometryXsdElement,
    GmlBoundedByElement,
    GmlIdAttribute,
    GmlNameElement,
    XPathMatch,
    XsdAnyType,
    XsdComplexType,
    XsdElement,
    XsdTypes,
)

if TYPE_CHECKING:
    from gisserver.projection import FeatureRelation

__all__ = [
    "FeatureType",
    "field",
    "FeatureField",
    "ComplexFeatureField",
]

logger = logging.getLogger(__name__)

XSD_TYPES = {
    models.CharField: XsdTypes.string,
    models.TextField: XsdTypes.string,
    models.BooleanField: XsdTypes.boolean,
    models.IntegerField: XsdTypes.integer,
    models.PositiveIntegerField: XsdTypes.nonNegativeInteger,
    models.PositiveBigIntegerField: XsdTypes.nonNegativeInteger,
    models.PositiveSmallIntegerField: XsdTypes.nonNegativeInteger,
    models.AutoField: XsdTypes.integer,  # Only as of Django 3.0 this extends from IntegerField
    models.FloatField: XsdTypes.double,
    models.DecimalField: XsdTypes.decimal,
    models.TimeField: XsdTypes.time,
    models.DateTimeField: XsdTypes.dateTime,  # note: DateTimeField extends DateField!
    models.DateField: XsdTypes.date,
    models.DurationField: XsdTypes.duration,
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


def _get_basic_field_type(
    field_name: str, model_field: models.Field | models.ForeignObjectRel
) -> XsdAnyType:
    """Determine the XSD field type for a Django field."""
    if ArrayField is not None and isinstance(model_field, ArrayField):
        # Determine the type based on the contents.
        # The array notation is written as "is_many"
        model_field = model_field.base_field

    if GeneratedField is not None and isinstance(model_field, GeneratedField):
        # Allow things like: models.GeneratedField(SomeFunction("geofield"), output_field=models.GeometryField())
        model_field = model_field.output_field

    try:
        # Direct instance, quickly resolved!
        return XSD_TYPES[model_field.__class__]
    except KeyError:
        pass

    if isinstance(model_field, models.ForeignKey):
        # Don't let it query on the relation value yet
        return _get_basic_field_type(field_name, model_field.target_field)
    elif isinstance(model_field, models.ForeignObjectRel):
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


def _get_model_fields(
    model: type[models.Model],
    fields: list[str] | Literal["__all__"],
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
            if not f.is_relation or f.many_to_one or f.one_to_one  # ForeignKey, OneToOneField
        ]
    else:
        # Only defined fields
        fields = [f if isinstance(f, FeatureField) else FeatureField(f) for f in fields]
        for field in fields:  # type: FeatureField
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
    xsd_element_class: type[XsdElement] = None

    model: type[models.Model] | None
    model_field: models.Field | models.ForeignObjectRel | None

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
        """
        Initialize a single field of the feature.

        :param name: Name of the model field.
        :param model_attribute: Which model attribute to access. This can be a dotted field path.
        :param model: Which model is accessed. Usually this is passed via :meth:`bind`.
        :param parent: The parent field of this element. Usually this is passed via :meth:`bind`.
        :param feature_type: The feature this field is a part of. Usually this is passed via :meth:`bind`.
        :param abstract: The "help text" or short abstract/description for this field.
        :param xsd_class: Override which class is used to construct the internal XsdElement.
                          This controls the schema rendering, value retrieval and rendering of the element.
        """
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
        self._nillable_output_field = False
        if model is not None:
            self.bind(model, parent=parent, feature_type=feature_type)

    def __repr__(self):
        if self.model_field is None:
            return f"<{self.__class__.__name__}: {self.name} (unbound)>"
        else:
            return (
                f"<{self.__class__.__name__}: {self.name}, source={self.absolute_model_attribute}>"
            )

    def _get_xsd_type(self):
        return _get_basic_field_type(self.name, self.model_field)

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

                for name in field_path[1:]:
                    if field.null:
                        self._nillable_relation = True

                    if not field.is_relation:
                        # Note this tests the previous loop variable, so it checks whether the
                        # field can be walked into in order to resolve the next dotted name below.
                        raise ImproperlyConfigured(
                            f"FeatureField '{self.name}' has an invalid model_attribute: "
                            f"field '{name}' is a '{field.__class__.__name__}', not a relation."
                        )

                    field = field.related_model._meta.get_field(name)
                self.model_field = field
            except FieldDoesNotExist as e:
                raise ImproperlyConfigured(
                    f"FeatureField '{self.name}' has an invalid"
                    f" model_attribute: '{self.model_attribute}' can't be"
                    f" resolved for model '{self.model.__name__}'."
                ) from e
        else:
            try:
                self.model_field = self.model._meta.get_field(self.name)
                if GeneratedField is not None and isinstance(self.model_field, GeneratedField):
                    self._nillable_output_field = self.model_field.output_field.null
            except FieldDoesNotExist as e:
                raise ImproperlyConfigured(
                    f"FeatureField '{self.name}' can't be resolved for model '{self.model.__name__}'."
                    " Either set 'model_attribute' or change the name."
                ) from e

    @cached_property
    def absolute_model_attribute(self) -> str:
        """Determine the full attribute of the field."""
        if self.model_field is None:
            raise RuntimeError(f"bind() was not called for {self!r}")

        if self.parent is not None:
            return f"{self.parent.absolute_model_attribute}.{self.model_attribute or self.name}"
        else:
            return self.model_attribute or self.name

    @cached_property
    def xsd_element(self) -> XsdElement:
        """Define the XMLSchema definition for a model field.

        This definition is used by the remaining application to access the
        data. It's the basis for DescribeFeatureType, and it's ``get_value()``
        method is read to access the model field data.
        """
        if self.model_field is None:
            raise RuntimeError(f"bind() was not called for {self!r}")

        xsd_type = self._get_xsd_type()

        # Determine max number of occurrences.
        if xsd_type.is_geometry:
            max_occurs = 1  # be explicit here, like mapserver does.
        elif self.model_field.many_to_many or self.model_field.one_to_many:
            max_occurs = "unbounded"  # M2M or reverse FK field
        elif ArrayField is not None and isinstance(self.model_field, ArrayField):
            max_occurs = self.model_field.size or "unbounded"
        else:
            max_occurs = None  # default is 1, but attribute can be left out.

        # Determine which subclass to use for the element.
        xsd_element_class = self.xsd_element_class or (
            GeometryXsdElement if xsd_type.is_geometry else XsdElement
        )

        return xsd_element_class(
            name=self.name,
            type=xsd_type,
            namespace=self.feature_type.xml_namespace,  # keep all types in the same namespace for now.
            nillable=(
                self.model_field.null or self._nillable_relation or self._nillable_output_field
            ),
            min_occurs=0,
            max_occurs=max_occurs,
            model_attribute=self.model_attribute,
            absolute_model_attribute=self.absolute_model_attribute,
            source=self.model_field,
            feature_type=self.feature_type,
        )


class ComplexFeatureField(FeatureField):
    """The configuration for an embedded relation field.

    This field type is suitable for any relational object, including
    foreign keys, reverse relations and M2M fields. The internal logic
    translates the relation into an embedded XSD complex type.
    """

    def __init__(
        self,
        name: str,
        fields: list[str | FeatureField] | Literal["__all__"],
        model_attribute=None,
        model=None,
        abstract=None,
        xsd_class=None,
        xsd_base_type=None,
    ):
        """
        :param name: Name of the model field.
        :param fields: If the field exposes a foreign key, provide its child element names.
            This can be a list of :func:`field` elements, or plain field names.
            Using ``__all__`` also works but is not recommended outside testing.
        :param model_attribute: Which model attribute to access. This can be a dotted field path.
        :param abstract: The "help text" or short abstract/description for this field.
        :param xsd_class: Override which class is used to construct the internal XsdElement.
                          This controls the schema rendering, value retrieval and rendering of the element.
        :param xsd_base_type: Override which class is the base class for the element.
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
        return _get_model_fields(
            self.target_model, self._fields, parent=self, feature_type=self.feature_type
        )

    def _get_xsd_type(self) -> XsdComplexType:
        """Generate the XSD description for the field with an object relation."""
        pk_field = self.target_model._meta.pk

        return XsdComplexType(
            name=f"{self.target_model._meta.object_name}Type",
            namespace=self.feature_type.xml_namespace,  # keep all types in the same namespace for now.
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
    fields: list[str | FeatureField] | Literal["__all__"] | None = None,
    xsd_class: type[XsdElement] | None = None,
) -> FeatureField:
    """Shortcut to define a WFS field.

    This automatically selects the proper field class,
    so little knowledge is needed about the internal working.

    :param name: Name of the model field.
    :param model_attribute: Which model attribute to access. This can be a dotted field path.
    :param abstract: The "help text" or short abstract/description for this field.
    :param fields: If the field exposes a foreign key, provide its child element names.
        This can be a list of :func:`field` elements, or plain field names.
        Using ``__all__`` also works but is not recommended outside testing.
    :param xsd_class: Override which class is used to construct the internal XsdElement.
                      This controls the schema rendering, value retrieval and rendering of the element.
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


class FeatureType:
    """Declare a feature that is exposed on the map.

    All WFS operations use this class to read the feature type.
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
        fields: list[str | FeatureField] | Literal["__all__"] | None = None,
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
        xml_namespace: str | None = None,
    ):
        """
        :param queryset: The queryset to retrieve the data.
        :param fields: Define which fields to show in the WFS data.
            This can be a list of field names, or :class:`FeatureField` objects.
        :param display_field_name: Name of the field that's used as general string representation.
        :param geometry_field_name: Name of the geometry field to expose (default = auto-detect).
        :param name: Name, also used as XML tag name.
        :param title: Used in WFS metadata.
        :param abstract: Used in WFS metadata.
        :param keywords: Used in WFS metadata.
        :param crs: Used in WFS metadata.
        :param other_crs: Used in WFS metadata.
        :param metadata_url: Used in WFS metadata.
        :param show_name_field: Whether to show the ``gml:name`` or the GeoJSON ``geometry_name``
            field. Default is to show a field when ``name_field`` is given.
        :param xml_namespace: The XML namespace to use, will be set by :meth:`bind_namespace` otherwise.
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
        self.xml_namespace = xml_namespace

        # Validate that the name doesn't require XML escaping.
        if html.escape(self.name) != self.name or " " in self.name or ":" in self.name:
            raise ValueError(f"Invalid feature name for XML: <{self.xml_name}>")

        self._cached_resolver = lru_cache(200)(self._inner_resolve_element)

    def __repr__(self):
        return (
            f"<{self.__class__.__qualname__}: {self.xml_name},"
            f" fields={self.fields!r},"
            f" geometry_field_name={self.main_geometry_element.absolute_model_attribute!r}>"
        )

    def bind_namespace(self, default_xml_namespace: str):
        """Make sure the feature type receives the settings from the parent view."""
        if not self.xml_namespace:
            self.xml_namespace = default_xml_namespace

    def check_permissions(self, request: HttpRequest):
        """Hook that allows subclasses to reject access for datasets.
        It may raise a Django PermissionDenied error.

        This can check for example whether ``request.user`` may access this feature.

        The parsed WFS request is available as ``request.ows_request``.
        Currently, this can be a :class:`~gisserver.parsers.wfs20.GetFeature`
        or :class:`~gisserver.parsers.wfs20.GetPropertyValue` instance.
        """

    @cached_property
    def xml_name(self) -> str:
        """Return the feature tag as XML Full Qualified name"""
        return f"{{{self.xml_namespace}}}{self.name}" if self.xml_namespace else self.name

    @cached_property
    def supported_crs(self) -> list[CRS]:
        """Return all spatial reference system ID's that this feature supports."""
        return [self.crs] + self.other_crs

    @cached_property
    def all_geometry_elements(self) -> list[GeometryXsdElement]:
        """Provide access to all geometry elements from *all* nested levels."""
        return self.xsd_type.geometry_elements + list(
            itertools.chain.from_iterable(
                # Take the geometry elements at each object level.
                xsd_element.type.geometry_elements
                for xsd_element in self.xsd_type.all_complex_elements
                # The 'None' level is the root node, which is already added before.
                # For now, don't support geometry fields on an M2M relation.
                # If that use-case is needed, it would require additional work to implement.
                if xsd_element is not None and not xsd_element.is_many
            )
        )

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
        if (
            self._geometry_field_name
            and "." in self._geometry_field_name
            and (self._fields is None or self._fields == "__all__")
        ):
            # If you want to define more complex relationships, please be explicit in which fields you want.
            # Allowing autoconfiguration of this is complex and likely not what you're looking for either.
            raise ImproperlyConfigured(
                "Using a geometry_field_name path requires defining 'fields' explicitly."
            )

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
            # Either __all__ or an explicit list.
            return _get_model_fields(self.model, self._fields, feature_type=self)

    @cached_property
    def display_field(self) -> models.Field | None:
        """Give access to the field that holds the string-representation."""
        if not self.show_name_field or not self.display_field_name:
            return None
        else:
            return self.model._meta.get_field(self.display_field_name)

    @cached_property
    def main_geometry_element(self) -> GeometryXsdElement:
        """Give access to the main geometry element."""
        if not self._geometry_field_name:
            try:
                # Take the first element that has a geometry.
                return self.all_geometry_elements[0]
            except IndexError:
                raise ImproperlyConfigured(
                    f"FeatureType '{self.name}' does not expose any geometry field "
                    f"as part of its definition."
                ) from None
        else:
            try:
                return next(
                    e
                    for e in self.all_geometry_elements
                    if e.absolute_model_attribute == self._geometry_field_name
                )
            except StopIteration:
                raise ImproperlyConfigured(
                    f"FeatureType '{self.name}' does not expose the geometry field "
                    f"'{self._geometry_field_name}' as part of its definition."
                ) from None

    @cached_property
    def crs(self) -> CRS:
        """Tell which projection the data should be presented at."""
        if self._crs is None:
            # Default CRS
            return CRS.from_srid(self.main_geometry_element.source_srid)  # checks lookup too
        else:
            return self._crs

    def get_queryset(self) -> models.QuerySet:
        """Return the queryset that is used as basis for this feature."""
        # Return a queryset that only retrieves the fields that are actually displayed.
        # That that without .only(), use at least `self.queryset.all()` so a clone is returned.
        logger.debug(
            "QuerySet for %s default only retrieves: %r",
            self.queryset.model._meta.label,
            self._local_model_field_names,
        )
        return self.queryset.only(*self._local_model_field_names)

    def get_related_queryset(self, feature_relation: FeatureRelation) -> models.QuerySet:
        """Return the queryset that is used for prefetching related data."""
        if feature_relation.related_model is None:
            raise RuntimeError(
                f"Unable to create prefetch queryset for relation {feature_relation.orm_path}, "
                f"source model is not defined for: {feature_relation.xsd_elements!r}"
            )
        # Return a queryset that only retrieves the fields that are displayed.
        logger.debug(
            "QuerySet for %s by default only retrieves: %r",
            feature_relation.related_model._meta.label,
            feature_relation._local_model_field_names,
        )
        queryset = feature_relation.related_model.objects.only(
            *feature_relation._local_model_field_names
        )
        return self.filter_related_queryset(queryset)  # Allow overriding by FeatureType subclasses

    def filter_related_queryset(self, queryset: models.QuerySet) -> models.QuerySet:
        """When a related object returns a queryset, this hook allows extra filtering."""
        return queryset

    def get_bounding_box(self) -> WGS84BoundingBox | None:
        """Returns a WGS84 BoundingBox for the complete feature.

        This is used by the GetCapabilities request. It may return ``None``
        when the database table is empty, or the custom queryset doesn't
        return any results.

        Note that the ``<ows:WGS84BoundingBox>`` element always uses longitude/latitude,
        as it doesn't describe a CRS.
        """
        if not self.main_geometry_element:
            return None

        return get_wgs84_bounding_box(self.get_queryset(), self.main_geometry_element)

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

        # Define <gml:boundedBy>
        base_elements = [GmlBoundedByElement(feature_type=self)]
        if self.show_name_field:
            # Add <gml:name>
            gml_name = GmlNameElement(
                model_attribute=self.display_field_name,
                source=self.display_field,
                feature_type=self,
            )
            base_elements.insert(0, gml_name)

        # Write out the definition of XsdTypes.gmlAbstractFeatureType as actual class definition.
        # By having these base elements, the XPath queries can also resolve these like any other feature field elements.
        return XsdComplexType(
            name="AbstractFeatureType",
            namespace=xmlns.gml.value,
            elements=base_elements,
            attributes=[
                # Add gml:id="..." attribute definition so it can be resolved in xpath
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
            name=f"{self.name[0].upper()}{self.name[1:]}Type",
            elements=[field.xsd_element for field in self.fields],
            namespace=self.xml_namespace,
            base=self.xsd_base_type,
            source=self.model,
        )

    def resolve_element(self, xpath: str, ns_aliases: dict[str, str]) -> XPathMatch:
        """Resolve the element, and the matching object.

        This is used to convert XPath references in requests
        to the actual elements and model attributes for queries.

        Internally, this method caches results.
        """
        # When the XML POST request used xmlns="http://www.opengis.net/wfs/2.0",
        # this will become the default namespace elements are translated into.
        # However, the XPath elements should be interpreted within our application namespace instead.
        # When the default namespace is missing, it should also resolve to our feature.
        ns_aliases = ns_aliases.copy()
        ns_aliases[""] = self.xml_namespace

        if len(ns_aliases) > 10:
            # Avoid filling memory by caching large namespace blobs.
            nodes = self._inner_resolve_element(xpath, ns_aliases)
        else:
            # Go through lru_cache() for faster lookup of the same elements.
            # Note 1: the cache will be less effective when clients use different namespace aliases.
            # Note 2: when WFSView overrides get_feature_types() the cache may only exist per request.
            nodes = self._cached_resolver(xpath, HDict(ns_aliases))

        if nodes is None:
            raise ExternalValueError(f"Field '{xpath}' does not exist.")

        return XPathMatch(self, nodes, query=xpath)

    def _inner_resolve_element(self, xpath: str, ns_aliases: dict[str, str]):
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

        # Allow /app:ElementName/.. as "absolute" path, simply strip it for now.
        # This is only actually needed to support join queries, which we don't.
        xpath = xpath.lstrip("/")
        root_name, _, _ = xpath.partition("/")
        root_xml_name = parse_qname(root_name, ns_aliases)
        if root_xml_name == self.xml_name:
            xpath = xpath[len(root_name) + 1 :]

        return self.xsd_type.resolve_element_path(xpath, ns_aliases)

    def resolve_crs(self, crs: CRS, locator="") -> CRS:
        """Check a parsed CRS against the list of supported types."""
        for candidate in self.supported_crs:
            # Not using self.supported_crs.index(crs), as that depends on CRS.__eq__():
            if candidate.matches(crs, compare_legacy=False):
                if candidate.force_xy != crs.force_xy:
                    # user provided legacy CRS, allow output in legacy CRS
                    return crs
                else:
                    # Replace the parsed CRS with the declared one.
                    return candidate

        # No match found
        if conf.GISSERVER_SUPPORTED_CRS_ONLY:
            raise InvalidParameterValue(
                f"Feature '{self.name}' does not support CRS '{crs}'.",
                locator=locator,
            ) from None
        else:
            return crs


class HDict(dict):
    """Dict that can be used in lru_cache()."""

    def __hash__(self):
        return hash(frozenset(self.items()))
