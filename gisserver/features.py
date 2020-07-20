"""Dataclasses that expose the metadata for the GetCapabilities call."""
import html
import operator
from dataclasses import dataclass
from functools import lru_cache, reduce
from typing import List, Optional, Type, Union

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models import Extent, GeometryField
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import cached_property  # py3.8: functools

from gisserver.db import conditional_transform
from gisserver.exceptions import ExternalValueError
from gisserver.types import (
    GmlBoundedByElement,
    GmlNameElement,
    XPathMatch,
    XsdAnyType,
    XsdComplexType,
    XsdElement,
    XsdTypes,
    GmlIdAttribute,
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


def get_basic_field_type(field_name: str, model_field: models.Field) -> XsdAnyType:
    """Determine the XSD field type for a Django field."""
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


def _get_target_model(model_field) -> Type[models.Model]:
    """Find which model a related field points at"""
    if isinstance(model_field, models.ForeignKey):
        return model_field.target_field.model
    elif isinstance(model_field, ForeignObjectRel):
        # e.g. ManyToOneRel descriptor of a foreignkey_id field.
        return model_field.remote_field.model
    else:
        raise NotImplementedError(
            f"Model field is not supported as relation: {model_field.__class__.__name__}"
        )


def _get_model_fields(model, fields, parent=None):
    if fields == "__all__":
        # All regular fields
        return [
            FeatureField(
                name=f.attname if isinstance(f, models.ForeignKey) else f.name,
                # .bind() is called directly:
                model=model,
                parent=parent,
            )
            for f in model._meta.get_fields()
        ]
    else:
        # Only defined fields
        fields = [f if isinstance(f, FeatureField) else FeatureField(f) for f in fields]
        for field in fields:
            field.bind(model, parent=parent)
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

    #: Allow to override the XSD element type that this field will generate.
    xsd_element_class: Type[XsdElement] = XsdElement

    model: Optional[Type[models.Model]]
    model_field: Optional[models.Field]

    def __init__(
        self,
        name,
        model_attribute=None,
        model=None,
        parent: "Optional[ComplexFeatureField]" = None,
    ):
        self.name = name
        self.model_attribute = model_attribute
        self.model = None
        self.model_field = None
        self.parent = parent
        self._nillable_relation = False
        if model is not None:
            self.bind(model)

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"

    def _get_xsd_type(self):
        return get_basic_field_type(self.name, self.model_field)

    def bind(
        self, model: Type[models.Model], parent: "Optional[ComplexFeatureField]" = None,
    ):
        """Late-binding for the model.

        This method is called internally when the field definition wasn't
        linked to a model yet. This allows the fields to be defined first,
        in external code, and then become part of the ``FeatureType`` fields
        list.

        :param model: The model is field is linked to.
        :param parent: When this element is part of a complex feature,
                       this links to the parent field.
        """
        if self.model is not None:
            raise RuntimeError(f"Feature field '{self.name}' cannot be reused")
        self.model = model
        self.parent = parent

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
                field = _get_target_model(field)._meta.get_field(name)
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

        return self.xsd_element_class(
            name=self.name,
            type=self._get_xsd_type(),
            nillable=self.model_field.null or self._nillable_relation,
            min_occurs=0,
            max_occurs=1 if isinstance(self.model_field, GeometryField) else None,
            model_attribute=self.model_attribute,
            source=self.model_field,
        )


_FieldDefinition = Union[str, FeatureField]
_FieldDefinitions = Union[_all_, List[_FieldDefinition]]


class ComplexFeatureField(FeatureField):
    """The configuration for an embedded foreign-key field.

    This translates the foreign key into an embedded XSD complex type.
    """

    def __init__(
        self, name: str, fields: _FieldDefinitions, model_attribute=None, model=None
    ):
        """
        :param name: Name of the model field.
        :param fields: List of fields to expose for the target model. This can
            be a list of :class:`FeatureField` objects, or plain field names.
            Using ``__all__`` also works but is not recommended outside testing.
        """
        super().__init__(name, model_attribute=model_attribute, model=model)
        self._fields = fields

    def _get_xsd_type(self) -> XsdComplexType:
        """Generate the XSD description for the field with an object relation."""
        fields = _get_model_fields(self.target_model, self._fields, parent=self)
        pk_field = self.target_model._meta.pk

        return XsdComplexType(
            name=f"{self.target_model._meta.object_name}Type",
            elements=[field.xsd_element for field in fields],
            attributes=[
                # Add gml:id attribute definition so it can be resolved in xpath
                GmlIdAttribute(
                    type_name=self.name, source=pk_field, model_attribute=pk_field.name,
                )
            ],
            source=self.target_model,
        )

    @property
    def target_model(self):
        """Detect which model the relation points to."""
        if self.model_field is None:
            raise RuntimeError("FeatureField.bind() is not called yet")

        try:
            return _get_target_model(self.model_field)
        except NotImplementedError:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} does not support fields of "
                f"type {self.model_field.__class__.__name__}."
            ) from None


def field(
    name: str, *, model_attribute=None, fields: Optional[_FieldDefinitions] = None
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
            name=name, model_attribute=model_attribute, fields=fields
        )
    else:
        return FeatureField(name, model_attribute=model_attribute)


class FeatureType:
    """Declare a feature that is exposed on the map.

    All WFS operations use this class to read the feature ype.
    You may subclass this class to provide extensions,
    such as redefining :meth:`get_queryset`.

    This corresponds with a single Django model.
    """

    #: Allow to override the XSD complex type that this feature will generate.
    xsd_type_class: Type[XsdComplexType] = XsdComplexType

    def __init__(
        self,
        queryset: models.QuerySet,
        *,
        fields: Optional[_FieldDefinitions] = None,
        display_field_name: str = None,
        geometry_field_name: str = None,
        name: str = None,
        # WFS Metadata:
        title: str = None,
        abstract: str = None,
        keywords: List[str] = None,
        crs: CRS = None,
        other_crs: List[CRS] = None,
        metadata_url: Optional[str] = None,
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

        # Auto-detect geometry fields (also fills geometry_field_name)
        self.geometry_fields = [
            f
            for f in self.model._meta.get_fields()
            if isinstance(f, gis_models.GeometryField)
        ]
        self._cached_resolver = lru_cache(100)(self._inner_resolve_element)

    def check_permissions(self, request):
        """Hook that allows subclasses to reject access for datasets.
        It may raise a Django PermissionDenied error.
        """
        pass

    @cached_property
    def xml_name(self):
        """Return the feature name with xml namespace prefix."""
        return f"{self.xml_prefix}:{self.name}"

    @cached_property
    def supported_crs(self) -> List[CRS]:
        """Return all spatial reference system ID's that this feature supports."""
        return [self.crs] + self.other_crs

    @cached_property
    def geometry_field_names(self):
        return {f.name for f in self.geometry_fields}

    @cached_property
    def fields(self) -> List[FeatureField]:
        """Define which fields to render."""
        # This lazy reading allows providing 'fields' as lazy value.
        if self._fields is None:
            return [FeatureField(self.geometry_field_name, model=self.model)]
        else:
            return _get_model_fields(self.model, self._fields)

    @cached_property
    def display_field(self) -> Optional[models.Field]:
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
        """Returns a WGS84 BoundingBox for the complete feature.

        This is used by the GetCapabilities request. It may return ``None``
        when the database table is empty, or the custom queryset doesn't
        return any results.
        """
        geo_expression = conditional_transform(
            self.geometry_field.name, self.geometry_field.srid, WGS84.srid
        )

        bbox = self.get_queryset().aggregate(a=Extent(geo_expression))["a"]
        return BoundingBox(*bbox, crs=WGS84) if bbox else None

    def get_envelope(
        self, instance, crs: Optional[CRS] = None
    ) -> Optional[BoundingBox]:
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
        geometry = (
            geometries[0] if len(geometries) == 1 else reduce(operator.or_, geometries)
        )
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

        return XsdComplexType(
            prefix="gml",
            name="AbstractFeatureType",
            elements=base_elements,
            attributes=[
                # Add gml:id attribute definition so it can be resolved in xpath
                GmlIdAttribute(
                    type_name=self.name, source=pk_field, model_attribute=pk_field.name,
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
            raise NotImplementedError(
                f"XPath selectors with functions are not supported: {xpath}"
            )

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
