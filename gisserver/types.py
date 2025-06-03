"""Internal XSD type definitions.

These types are the internal schema definition, and the foundation for all output generation.

The end-users of this library typically create a WFS feature type definition by using
the :class:`~gisserver.features.FeatureType` / :class:`~gisserver.features.FeatureField` classes.

The feature type classes use the model metadata to construct the internal XMLSchema structure.
Nearly all WFS requests are handled by walking this structure (like ``DescribeFeatureType``
or ``GetFeature``). The rendered output is created by walking through this structure,
and writing the XML elements. All search queries (using XPath) are processed by
resolving the corresponding element/attributes, to find to the underlying Django model field.

The structure has the following elements:

* :class:`XsdElement` to define the schema of a single XML element (``<xsd:element>``).
* :class:`XsdAttribute` to define the schema of a single XML attribute (``<xsd:attribute>``).

Each XMLSchema node defines it's "data type" as either:

* :class:`XsdTypes` for simple well-known data types (e.g. text/int, etc..)
* :class:`XsdComplexType` for a complete class definition (holding elements and attributes)

Custom field types could also generate these field types.
"""

from __future__ import annotations

import logging
import operator
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal as D
from enum import Enum
from functools import cached_property
from typing import TYPE_CHECKING, Literal

import django
from django.contrib.gis.db.models import F, GeometryField
from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.fields.related import RelatedField

from gisserver.compat import ArrayField, GeneratedField
from gisserver.crs import CRS
from gisserver.exceptions import ExternalParsingError, OperationProcessingFailed
from gisserver.geometries import BoundingBox
from gisserver.parsers import values
from gisserver.parsers.xml import parse_qname, split_ns, xmlns

logger = logging.getLogger(__name__)

__all__ = [
    "GeometryXsdElement",
    "GmlIdAttribute",
    "GmlNameElement",
    "GmlBoundedByElement",
    "ORMPath",
    "XPathMatch",
    "XsdAnyType",
    "XsdAttribute",
    "XsdComplexType",
    "XsdElement",
    "XsdNode",
    "XsdTypes",
]

RE_XPATH_ATTR = re.compile(r"\[[^\]]+\]$")  # match [@attr=..]


class XsdAnyType:
    """Base class for all types used in the XML definition.
    This includes the enum values (:class:`XsdTypes`) for well-known types,
    adn the :class:`XsdComplexType` that represents a while class definition.
    """

    #: Local name of the XML element
    name: str

    #: Namespace of the XML element
    namespace = None

    #: Whether this is a complex type
    is_complex_type = False

    #: Whether this is a geometry
    is_geometry = False  # Overwritten for some gml types.

    def __str__(self):
        """Return the type name (in full XML format)"""
        raise NotImplementedError()

    def to_python(self, raw_value):
        """Convert a raw string value to this type representation"""
        return raw_value


class XsdTypes(XsdAnyType, Enum):
    """Brief enumeration of common XMLSchema types.

    The :class:`XsdElement` and :class:`XsdAttribute` can use these enum members
    to indicate their value is a well-known XML Schema. Some GML types are included as well.

    Each member value is a fully qualified XML name.
    The output rendering will convert these to the chosen prefixes.
    """

    anyType = xmlns.xs.qname("anyType")  # not "xsd:any", that is an element.
    string = xmlns.xs.qname("string")
    boolean = xmlns.xs.qname("boolean")
    decimal = xmlns.xs.qname("decimal")  # the base type for all numbers too.
    integer = xmlns.xs.qname("integer")  # integer value
    float = xmlns.xs.qname("float")
    double = xmlns.xs.qname("double")
    time = xmlns.xs.qname("time")
    date = xmlns.xs.qname("date")
    dateTime = xmlns.xs.qname("dateTime")
    anyURI = xmlns.xs.qname("anyURI")

    # Number variations
    byte = xmlns.xs.qname("byte")  # signed 8-bit integer
    short = xmlns.xs.qname("short")  # signed 16-bit integer
    int = xmlns.xs.qname("int")  # signed 32-bit integer
    long = xmlns.xs.qname("long")  # signed 64-bit integer
    unsignedByte = xmlns.xs.qname("unsignedByte")  # unsigned 8-bit integer
    unsignedShort = xmlns.xs.qname("unsignedShort")  # unsigned 16-bit integer
    unsignedInt = xmlns.xs.qname("unsignedInt")  # unsigned 32-bit integer
    unsignedLong = xmlns.xs.qname("unsignedLong")  # unsigned 64-bit integer

    # Less common, but useful nonetheless:
    duration = xmlns.xs.qname("duration")
    nonNegativeInteger = xmlns.xs.qname("nonNegativeInteger")
    gYear = xmlns.xs.qname("gYear")
    hexBinary = xmlns.xs.qname("hexBinary")
    base64Binary = xmlns.xs.qname("base64Binary")
    token = xmlns.xs.qname("token")  # noqa: S105
    language = xmlns.xs.qname("language")

    # Types that contain a GML value as member:
    # Note these receive the "is_geometry = True" value below.
    gmlGeometryPropertyType = xmlns.gml.qname("GeometryPropertyType")
    gmlPointPropertyType = xmlns.gml.qname("PointPropertyType")
    gmlCurvePropertyType = xmlns.gml.qname("CurvePropertyType")  # curve is base for LineString
    gmlSurfacePropertyType = xmlns.gml.qname("SurfacePropertyType")  # GML2 had PolygonPropertyType
    gmlMultiSurfacePropertyType = xmlns.gml.qname("MultiSurfacePropertyType")
    gmlMultiPointPropertyType = xmlns.gml.qname("MultiPointPropertyType")
    gmlMultiCurvePropertyType = xmlns.gml.qname("MultiCurvePropertyType")
    gmlMultiGeometryPropertyType = xmlns.gml.qname("MultiGeometryPropertyType")

    # Other typical GML values:

    #: The type for ``<gml:name>`` elements.
    gmlCodeType = xmlns.gml.qname("CodeType")  # for <gml:name>

    #: The type for ``<gml:boundedBy>`` elements.
    gmlBoundingShapeType = xmlns.gml.qname("BoundingShapeType")

    #: The type for ``<gml:Envelope>`` elements, sometimes used as function argument type.
    gmlEnvelopeType = xmlns.gml.qname("EnvelopeType")

    #: A direct geometry value, sometimes used as function argument type.
    gmlAbstractGeometryType = xmlns.gml.qname("AbstractGeometryType")

    #: A feature that has a gml:name and gml:boundedBy as possible child element.
    gmlAbstractFeatureType = xmlns.gml.qname("AbstractFeatureType")

    #: The base of gml:AbstractFeatureType
    gmlAbstractGMLType = xmlns.gml.qname("AbstractGMLType")

    def __str__(self):
        return self.value

    def __init__(self, value):
        # Parse XML namespace data once, which to_qname() uses.
        # Can't set enum.name, so will use a property for that.
        self.namespace, self._localname = split_ns(value)
        self.is_geometry = False  # redefined below

    @cached_property
    def name(self) -> str:
        """Overwrites enum.name to return the XML local name.
        This is used for to_qname().
        """
        return self._localname

    @cached_property
    def _to_python_func(self):
        try:
            return TYPES_TO_PYTHON[self]
        except KeyError:
            raise NotImplementedError(f'Casting to "{self}" is not implemented.') from None

    def to_python(self, raw_value):
        """Convert a raw string value to this type representation.

        :raises ExternalParsingError: When the value can't be converted to the proper type.
        """
        if self.is_geometry or isinstance(raw_value, TYPES_AS_PYTHON[self]):
            # Detect when the value was already parsed, no need to reparse a date for example.
            return raw_value

        try:
            return self._to_python_func(raw_value)
        except ExternalParsingError:
            raise  # subclass of ValueError so explicitly caught and reraised
        except (TypeError, ValueError, ArithmeticError) as e:
            # ArithmeticError is base of DecimalException
            logger.debug("Parsing error for %r: %s", raw_value, e)
            name = self.name if self.namespace == xmlns.xsd.value else self.value
            raise ExternalParsingError(f"Can't cast '{raw_value}' to {name}.") from e


for _type in (
    XsdTypes.gmlGeometryPropertyType,
    XsdTypes.gmlPointPropertyType,
    XsdTypes.gmlCurvePropertyType,
    XsdTypes.gmlSurfacePropertyType,
    XsdTypes.gmlMultiSurfacePropertyType,
    XsdTypes.gmlMultiPointPropertyType,
    XsdTypes.gmlMultiCurvePropertyType,
    XsdTypes.gmlMultiGeometryPropertyType,
    # gml:boundedBy is technically a geometry, which we don't support in queries currently.
    XsdTypes.gmlBoundingShapeType,
):
    # One of the reasons the code checks for "xsd_element.type.is_geometry"
    # is because profiling showed that isinstance(xsd_element, ...) is really slow.
    # When rendering 5000 objects with 10+ elements, isinstance() started showing up as hotspot.
    _type.is_geometry = True


def _as_is(v):
    return v


TYPES_AS_PYTHON = {
    XsdTypes.date: date,
    XsdTypes.dateTime: datetime,
    XsdTypes.time: time,
    XsdTypes.string: str,
    XsdTypes.boolean: bool,
    XsdTypes.integer: int,
    XsdTypes.int: int,
    XsdTypes.long: int,
    XsdTypes.short: int,
    XsdTypes.byte: int,
    XsdTypes.unsignedInt: int,
    XsdTypes.unsignedLong: int,
    XsdTypes.unsignedShort: int,
    XsdTypes.unsignedByte: int,
    XsdTypes.float: D,  # auto_cast() always converts to decimal
    XsdTypes.double: D,
    XsdTypes.decimal: D,
    XsdTypes.duration: timedelta,
    XsdTypes.nonNegativeInteger: int,
    XsdTypes.gYear: int,
    XsdTypes.hexBinary: bytes,
    XsdTypes.base64Binary: bytes,
    XsdTypes.token: str,
    XsdTypes.language: str,
    XsdTypes.gmlCodeType: str,
    XsdTypes.anyType: type(Ellipsis),
}

TYPES_TO_PYTHON = {
    **TYPES_AS_PYTHON,
    XsdTypes.date: values.parse_iso_date,
    XsdTypes.dateTime: values.parse_iso_datetime,
    XsdTypes.time: values.parse_iso_time,
    XsdTypes.string: _as_is,
    XsdTypes.boolean: values.parse_bool,
    XsdTypes.duration: values.parse_iso_duration,
    XsdTypes.gmlCodeType: _as_is,
    XsdTypes.anyType: values.auto_cast,
}


class XsdNode:
    """Base class for :class:`XsdElement` and :class:`XsdAttribute`.

    This contains all common mapping/resolving that both elements and attributes share.
    For instance, how XML nodes are mapped into ORM paths, converted into ORM filters,
    parse query input and read model attributes to write as output.
    """

    #: Whether this node is an :class:`XsdAttribute` (avoids slow ``isinstance()`` checks)
    is_attribute = False
    #: Whether this node can occur multiple times.
    is_many = False

    #: The local name of the XML element
    name: str

    #: The data type of the element/attribute, both :class:`XsdComplexType` and :class:`XsdTypes` are allowed.
    type: XsdAnyType

    #: XML Namespace of the element
    namespace: xmlns | str | None

    #: Which field to read from the model to get the value
    #: This supports dot notation to access related attributes.
    source: models.Field | models.ForeignObjectRel | None

    #: Which field to read from the model to get the value
    #: This supports dot notation to access related attributes.
    model_attribute: str | None

    #: A link back to the parent that described the feature this node is a part of.
    #: This helps to perform additional filtering in side meth:get_value: based on user policies.
    feature_type: FeatureType | None

    def __init__(
        self,
        name: str,
        type: XsdAnyType,
        namespace: xmlns | str | None,
        *,
        source: models.Field | models.ForeignObjectRel | None = None,
        model_attribute: str | None = None,
        absolute_model_attribute: str | None = None,
        feature_type: FeatureType | None = None,
    ):
        """
        :param name: The local name of the element.
        :param type: The XML Schema type of the element, can also be a XsdComplexType.
        :param namespace: XML namespace URI.
        :param source: Original Model field, which can provide more metadata/parsing.
        :param model_attribute: The Django model path that this element accesses.
        :param absolute_model_attribute: The full path, including parent elements.
        :param feature_type: Typically assigned in :meth:`~gisserver.features.FeatureField.bind`,
                             needed by some :meth:`get_value` functions.
        """
        if ":" in name:
            raise ValueError(
                "XsdNode should receive the localname, not the QName in ns:localname format."
            )
        elif "}" in name:
            raise ValueError(
                "XsdNode should receive the localname, not the full name in {uri}name format."
            )

        # Using plain assignment instead of dataclass turns out to be needed
        # for flexibility and easier subclassing.
        self.name = name
        self.type = type
        self.namespace = str(namespace) if namespace is not None else None  # cast enum members.
        self.source = source
        self.model_attribute = model_attribute or self.name
        self.absolute_model_attribute = absolute_model_attribute or self.model_attribute
        # link back to top-level parent, some get_value() functions need it.
        self.feature_type = feature_type

        if (
            self.model_attribute
            and self.absolute_model_attribute
            and not self.absolute_model_attribute.endswith(self.model_attribute)
        ):
            raise ValueError("Inconsistent 'absolute_model_attribute' and 'model_attribute' value")

        self._attrgetter = operator.attrgetter(self.model_attribute)
        self._valuegetter = self._build_valuegetter(self.model_attribute, self.source)

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}: {self.xml_name}"
            f", model_attribute={self.model_attribute}>"
        )

    @staticmethod
    def _build_valuegetter(
        model_attribute: str,
        field: models.Field | models.ForeignObjectRel | None,
    ):
        """Select the most efficient read function to retrieves the value.

        Since reading a value can be called like 150000+ times, this is heavily optimized.

        This attempts to use ``operator.attrgetter()`` whenever possible,
        since this will be much faster than using ``getattr()``.
        The custom ``value_from_object()`` is fully supported too.
        """
        if field is None or isinstance(field, models.ForeignObjectRel):
            # No model field, can only use getattr(). The attrgetter() function is both faster,
            # and has built-in support for traversing model attributes with dots.
            return operator.attrgetter(model_attribute)

        if field.value_from_object.__func__ is models.Field.value_from_object:
            # No custom value_from_object(), this can be fully emulated with attrgetter() too.
            # Still allow the final node to have a custom attname,
            # which is what Field.value_from_object() does.
            names = model_attribute.split(".")
            names[-1] = field.attname
            return operator.attrgetter(".".join(names))

        if "." not in model_attribute:
            # Single level, use the custom value_from_object() directly.
            return field.value_from_object

        # Need to traverse the related field path, and use value_from_object() on the final object.
        names = model_attribute.split(".")
        get_related_instance = operator.attrgetter(".".join(names[:-1]))

        def _related_get_value_from_object(instance):
            related_instance = get_related_instance(instance)
            return field.value_from_object(related_instance)

        return _related_get_value_from_object

    @cached_property
    def is_array(self) -> bool:
        """Tell whether this node is backed by an PostgreSQL Array Field."""
        return ArrayField is not None and isinstance(self.source, ArrayField)

    @cached_property
    def is_flattened(self) -> bool:
        """Whether the field is a lookup to a relation."""
        return "." in self.model_attribute

    @cached_property
    def xml_name(self):
        """The XML element/attribute name."""
        return f"{{{self.namespace}}}{self.name}" if self.namespace else self.name

    def relative_orm_path(self, parent: XsdElement | None = None) -> str:
        """The ORM field lookup to perform, relative to the parent element."""
        if parent is None:
            return self.orm_path

        prefix = f"{parent.orm_path}__"
        if not self.orm_path.startswith(prefix):
            raise ValueError(f"Node '{self}' is not a child of '{parent}.")
        else:
            return self.orm_path[len(prefix) :]

    @cached_property
    def local_orm_path(self) -> str:
        """The ORM field lookup to perform."""
        if self.model_attribute is None:
            raise ValueError(f"Node {self.xml_name} has no 'model_attribute' set.")
        return self.model_attribute.replace(".", "__")

    @cached_property
    def orm_path(self) -> str:
        """The ORM field lookup to perform."""
        if self.absolute_model_attribute is None:
            raise ValueError(f"Node {self.xml_name} has no 'absolute_model_attribute' set.")
        return self.absolute_model_attribute.replace(".", "__")

    @cached_property
    def orm_field(self) -> str:
        """The direct ORM field that provides this property; the first relative level.
        Typically, this is the same as the field name.
        """
        return self.orm_path.partition(".")[0]

    @cached_property
    def orm_relation(self) -> tuple[str | None, str]:
        """The ORM field and parent relation.
        Note this isn't something like "self.parent.orm_path",
        as this mode may have a dotted-path to its source attribute.
        """
        path, _, field = self.orm_path.rpartition("__")
        return path or None, field

    def build_lhs_part(self, compiler: CompiledQuery, match: ORMPath):
        """Give the ORM part when this element is used as left-hand-side of a comparison.
        This is needed for queries like "<element> == <value>"
        """
        return match.orm_path

    def build_rhs_part(self, compiler: CompiledQuery, match: ORMPath):
        """Give the ORM part when this element would be used as right-hand-side.
        This is needed for queries like "<value> == <element>" or "<element> == <element>".
        """
        return F(match.orm_path)

    def get_value(self, instance: models.Model):
        """Provide the value for the data"""
        # For foreign keys, it's not possible to use the model value,
        # as that would conflict with the field type in the XSD schema.
        try:
            if self.type.is_complex_type:
                # This element has sub elements, which need the Django model instance.
                # Avoid unwanted value_from_object(), instead return the model instance.
                value = self._attrgetter(instance)
                if self.is_many and isinstance(value, models.Manager):
                    # Make sure callers can read the individual items by iterating over the value.
                    value = value.all()
                    if self.feature_type is not None:
                        return self.feature_type.filter_related_queryset(value)
                return value
            else:
                # the _valuegetter() supports value_from_object() on custom fields.
                return self._valuegetter(instance)
        except (AttributeError, ObjectDoesNotExist):
            # E.g. Django foreign keys that point to a non-existing member.
            return None

    def format_raw_value(self, value):
        """Allow to apply some final transformations on a value.
        This is mainly used to support @gml:id which includes a prefix.
        """
        return value

    def to_python(self, raw_value: str):
        """Convert a raw value to the Python data type for this element type.
        :raises ValidationError: When the value isn't allowed for the field type.
        """
        try:
            raw_value = self.type.to_python(raw_value)
            if self.source is not None:
                raw_value = self.source.get_prep_value(raw_value)
        except ValidationError as e:
            raise ValidationError(
                f"Invalid data for the '{self.name}' property: {e.messages[0]}",
                code=e.code,
            ) from e
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid data for the '{self.name}' property: {e}") from e

        return raw_value

    def validate_comparison(self, raw_value: str, lookup, tag=None):
        """Validate whether the input value can be used in a comparison.
        This avoids comparing a database DATETIME object to an integer.

        The raw string value can be passed here. Auto-cased values could
        raise an TypeError due to being unsupported by the validation.

        :param raw_value: The string value taken from the XML node.
        :param lookup: The ORM lookup (e.g. ``equals`` or ``fes_like``).
        :param tag: The filter operator tag name, e.g. ``PropertyIsEqualTo``.
        :returns: The parsed Python value.
        """
        # Not calling self.source.validate() as that checks for allowed choices,
        # which shouldn't be checked against for a filter query.
        raw_value = self.to_python(raw_value)

        # Check whether the Django model field supports the lookup
        # This prevents calling LIKE on a datetime or float field.
        # For foreign keys, this depends on the target field type.
        if (
            self.source is not None
            and self.source.get_lookup(lookup) is None
            or (
                isinstance(self.source, RelatedField)
                and self.source.target_field.get_lookup(lookup) is None
            )
        ):
            logger.debug(
                "Model field '%s.%s' does not support ORM lookup '%s' used by '%s'.",
                self.feature_type.model._meta.model_name,
                self.absolute_model_attribute,
                lookup,
                tag,
            )
            raise OperationProcessingFailed(
                f"Operator '{tag}' is not supported for the '{self.name}' property.",
                locator="filter",
                status_code=400,  # not HTTP 500 here. Spec allows both.
            )

        return raw_value


class XsdElement(XsdNode):
    """Declare an XSD element.

    Typically, this maps into a Django model field.

    This holds the definition for a single property in the WFS server.
    It's used in ``DescribeFeatureType`` to output the field metadata,
    and used in ``GetFeature`` to access the actual value from the object.
    Overriding :meth:`XsdNode.get_value` allows to override this logic.

    The :attr:`name` may differ from the underlying :attr:`XsdNode.model_attribute`,
    so the WFS server can use other field names then the underlying model.

    A dotted-path notation can be used for :attr:`XsdNode.model_attribute` to access
    a related field. For the WFS client, the data appears to be flattened.
    """

    #: Whether the element can be null
    nillable: bool | None
    #: The minimal number of times the element occurs in the output.
    min_occurs: int | None
    #: The maximum number of times this element occurs in the output.
    max_occurs: int | Literal["unbounded"] | None

    def __init__(
        self,
        name: str,
        type: XsdAnyType,
        namespace: xmlns | str | None,
        *,
        nillable: bool | None = None,
        min_occurs: int | None = None,
        max_occurs: int | Literal["unbounded"] | None = None,
        source: models.Field | models.ForeignObjectRel | None = None,
        model_attribute: str | None = None,
        absolute_model_attribute: str | None = None,
        feature_type: FeatureType | None = None,
    ):
        super().__init__(
            name,
            type,
            namespace=namespace,
            source=source,
            model_attribute=model_attribute,
            absolute_model_attribute=absolute_model_attribute,
            feature_type=feature_type,
        )
        self.nillable = nillable
        self.min_occurs = min_occurs
        self.max_occurs = max_occurs

    @cached_property
    def is_many(self) -> bool:
        """Tell whether the XML element can be rendered multiple times.
        Note this happens both with array fields and "..._to_many" relations.
        """
        return self.max_occurs and (
            self.max_occurs == "unbounded"
            or self.max_occurs > 1
            # needed for ArrayField(size=1):
            or (ArrayField is not None and isinstance(self.source, ArrayField))
        )


class _XsdElement_WithComplexType(XsdElement):
    """This only exists as "protocol" for the type annotations"""

    type: XsdComplexType


class XsdAttribute(XsdNode):
    """Declare an XSD attribute.

    Typically, this maps into a Django model field.

    Most fields are mapped into XML Elements (:class:`XsdElement`).
    However, WFS also supports XML attributes, and queries against them.
    This class is uses to support filters against attributes like "gml:id".
    """

    is_attribute = True

    type: XsdTypes
    use: str = "optional"

    def __init__(
        self,
        name: str,
        type: XsdAnyType = XsdTypes.string,  # added default
        *,
        namespace: xmlns | str | None = None,
        use: str = "optional",
        source: models.Field | models.ForeignObjectRel | None = None,
        model_attribute: str | None = None,
        absolute_model_attribute: str | None = None,
        feature_type: FeatureType | None = None,
    ):
        super().__init__(
            name,
            type,
            namespace=namespace,
            source=source,
            model_attribute=model_attribute,
            absolute_model_attribute=absolute_model_attribute,
            feature_type=feature_type,
        )
        self.use = use


class GeometryXsdElement(XsdElement):
    """A subtype for the :class:`XsdElement` that provides access to geometry data.

    This declares an element such as::

        <app:geometry>
            <gml:Point>...</gml:Point>
        </app:geometry>

    Hence, the :attr:`namespace` of this element isn't the GML namespace,
    only the type it points to is geometry data.

    The :attr:`source` is guaranteed to point to a :class:`~django.contrib.gis.models.GeometryField`,
    and can be a :class:`~django.db.models.GeneratedField` in Django 5
    as long as its ``output_field`` points to a :class:`~django.contrib.gis.models.GeometryField`.
    """

    if django.VERSION >= (5, 0):
        source: GeometryField | models.GeneratedField
    else:
        source: GeometryField

    @cached_property
    def source_srid(self) -> int:
        """Tell which Spatial Reference Identifier the source information is stored under."""
        if GeneratedField is not None and isinstance(self.source, GeneratedField):
            # Allow GeometryField to be wrapped as:
            # models.GeneratedField(SomeFunction("geofield"), output_field=models.GeometryField())
            return self.source.output_field.srid
        else:
            return self.source.srid


class GmlIdAttribute(XsdAttribute):
    """A virtual ``gml:id="..."`` attribute that can be queried.
    This subclass has overwritten :meth:`get_value` logic to format the value.
    """

    type_name: str

    def __init__(
        self,
        type_name: str,
        source: models.Field | models.ForeignObjectRel | None = None,
        model_attribute="pk",
        absolute_model_attribute=None,
        feature_type: FeatureType | None = None,
    ):
        super().__init__(
            name="id",
            namespace=xmlns.gml,
            source=source,
            model_attribute=model_attribute,
            absolute_model_attribute=absolute_model_attribute,
            feature_type=feature_type,
        )
        object.__setattr__(self, "type_name", type_name)

    def get_value(self, instance: models.Model):
        """Render the value."""
        pk = super().get_value(instance)  # handle dotted-name notations
        return f"{self.type_name}.{pk}"

    def format_raw_value(self, value):
        """Format the value as retrieved from the database."""
        return f"{self.type_name}.{value}"


class GmlNameElement(XsdElement):
    """A subclass to handle the ``<gml:name>`` element.
    This displays a human-readable title for the object.

    Currently, this just reads a single attribute,
    but it can be extended to support formatted names
    (although that would make comparisons on ``element@gml:name`` more complex).
    """

    def __init__(
        self,
        model_attribute: str,
        source: models.Field | models.ForeignObjectRel | None = None,
        feature_type=None,
    ):
        # Prefill most known fields
        super().__init__(
            name="name",
            type=XsdTypes.gmlCodeType,
            namespace=xmlns.gml,
            min_occurs=0,
            source=source,
            model_attribute=model_attribute,
            feature_type=feature_type,
        )

    def get_value(self, instance: models.Model):
        """Override value retrieval to retrieve the value from the feature type."""
        if self.feature_type is not None:
            # Let FeatureType provide a nice display/title for the object.
            return self.feature_type.get_display_value(instance)
        else:
            # Fallback, when using this class at a sub-level object.
            return super().get_value(instance)


class GmlBoundedByElement(XsdElement):
    """A subclass to handle the ``<gml:boundedBy>`` element.

    This override makes sure this non-model element data
    can be included in the XML tree like every other element.
    Its value is the complete bounding box of the feature type data.
    """

    def __init__(self, feature_type):
        # Prefill most known fields
        super().__init__(
            name="boundedBy",
            type=XsdTypes.gmlBoundingShapeType,
            namespace=xmlns.gml,
            min_occurs=0,
            feature_type=feature_type,
        )
        self.model_attribute = None

    def build_lhs_part(self, compiler: CompiledQuery, match: ORMPath):
        """Give the ORM part when this element is used as
        left-hand-side of a comparison."""
        return compiler.add_annotation(self.build_rhs_part(compiler, match))

    def build_rhs_part(self, compiler: CompiledQuery, match: ORMPath):
        """Give the ORM part when this element would be used as right-hand-side"""
        raise NotImplementedError("queries against <gml:boundedBy> are not supported")

    def get_value(self, instance: models.Model, crs: CRS | None = None) -> BoundingBox | None:
        """Provide the value of the <gml:boundedBy> field,
        which is the bounding box for a single instance.

        This is only used for native Python rendering. When the database
        rendering is enabled (GISSERVER_USE_DB_RENDERING=True), the calculation
        is entirely performed within the query.
        """
        geometries: list[GEOSGeometry] = list(
            # remove 'None' values
            filter(
                None,
                [
                    # support dotted paths here for geometries in a foreign key relation.
                    operator.attrgetter(geo_element.absolute_model_attribute)(instance)
                    for geo_element in self.feature_type.all_geometry_elements
                ],
            )
        )
        if not geometries:
            return None

        return BoundingBox.from_geometries(geometries, crs)


@dataclass(frozen=True)
class XsdComplexType(XsdAnyType):
    """Define an ``<xsd:complexType>`` that represents a whole class definition.

    Typically, this maps into a Django model, with each element pointing to a model field.
    For example:

    .. code-block:: python

        XsdComplexType(
            "PersonType",
            elements=[
                XsdElement("name", type=XsdTypes.string),
                XsdElement("age", type=XsdTypes.integer),
                XsdElement("address", type=XsdComplexType(
                    "AddressType",
                    elements=[
                        XsdElement("street", type=XsdTypes.string),
                        ...
                    ]
                )),
            ],
            attributes=[
                XsdAttribute("id", type=XsdTypes.integer),
            ],
        )

    A complex type can hold multiple :class:`XsdElement` and :class:`XsdAttribute`
    nodes as children, composing an object. Its :attr:`base` may point to a :class:`XsdComplexType`
    as base class, allowing to define those inherited elements too.

    Each element can be a complex type themselves, to create a nested class structure.
    That also allows embedding models with their relations into a single response.

    .. note:: Good to know
        This object definition is the internal "source of truth" regarding
        which field names and field elements are used in the WFS server:

        * The ``DescribeFeatureType`` request uses this definition to render the matching XMLSchema.
        * Incoming XPath queries are parsed using this object to resolve the XPath to model attributes.

    Objects of this type are typically generated by the :class:`~gisserver.features.FeatureType` and
    :class:`~gisserver.features.ComplexFeatureField` classes, using the Django model data.

    By default, The :attr:`base` type is detected as ``<gml:AbstractFeatureType>``,
    when there is a geometry element in the definition.
    """

    #: Internal class name (without XML namespace/prefix)
    name: str

    #: The XML namespace
    namespace: str | None

    #: All local elements in this class
    elements: list[XsdElement] = field(default_factory=list)

    #: All attributes in this class
    attributes: list[XsdAttribute] = field(default_factory=list)

    #: The base class of this type. Typically gml:AbstractFeatureType,
    #: which provides the <gml:name> and <gml:boundedBy> elements.
    base: XsdAnyType | None = None

    #: The Django model class that this type was based on.
    source: type[models.Model] | None = None

    def __post_init__(self):
        # Autodetect (or autocorrect) to have the proper base class when gml elements are present.
        if self.base is None:
            if any(e.type.is_geometry for e in self.elements):
                # for <gml:name> and <gml:boundedBy> elements.
                self.__dict__["base"] = XsdTypes.gmlAbstractFeatureType
            elif any(e.type is XsdTypes.gmlCodeType for e in self.elements):
                # for <gml:name> only
                self.__dict__["base"] = XsdTypes.gmlAbstractGMLType

    def __str__(self):
        return self.xml_name

    @cached_property
    def xml_name(self):
        """Name in the XMLSchema (e.g. {http://example.org/namespace}:SomeClass)."""
        return f"{{{self.namespace}}}{self.name}" if self.namespace else self.name

    @property
    def is_complex_type(self) -> bool:
        """Always indicates this is a complex type."""
        return True  # a property to avoid being used as field.

    @cached_property
    def elements_including_base(self) -> list[XsdElement]:
        """The local and inherited elements of this XSD type."""
        if self.base is not None and self.base.is_complex_type:
            # Add all base class members, in their correct ordering
            # By having these as XsdElement objects instead of hard-coded writes,
            # the query/filter logic also works for these elements.
            return self.base.elements + self.elements
        else:
            return self.elements

    @cached_property
    def geometry_elements(self) -> list[GeometryXsdElement]:
        """Shortcut to get all geometry elements"""
        return [e for e in self.elements if e.type.is_geometry]

    @cached_property
    def complex_elements(self) -> list[_XsdElement_WithComplexType]:
        """Shortcut to get all elements with a complex type.
        To get all complex elements recursively, read :attr:`all_complex_elements`.
        """
        return [e for e in self.elements if e.type.is_complex_type]

    @cached_property
    def flattened_elements(self) -> list[XsdElement]:
        """Shortcut to get all elements with a flattened model attribute"""
        return [e for e in self.elements if e.is_flattened]

    @cached_property
    def all_complex_elements(self) -> list[_XsdElement_WithComplexType]:
        """Shortcut to get all elements with children.
        This mainly exists to provide a structure to mimic what's used
        when PROPERTYNAME is part of the request.
        """
        child_nodes = []
        for xsd_element in self.complex_elements:
            child_nodes.append(xsd_element)
            child_nodes.extend(xsd_element.type.all_complex_elements)
        return child_nodes

    def resolve_element_path(self, xpath: str, ns_aliases: dict[str, str]) -> list[XsdNode] | None:
        """Resolve a xpath reference to the actual node.
        This returns the whole path, including in-between relations, if a match was found.

        This is used by :meth:`~gisserver.features.FeatureType.resolve_element`
        to convert a request XPath element into the ORM attributes for database queries.
        """
        try:
            pos = xpath.index("/")
            node_name = xpath[:pos]
        except ValueError:
            node_name = xpath
            pos = 0

        # Strip any [@attr=..] conditions
        node_name = RE_XPATH_ATTR.sub("", node_name)

        if node_name.startswith("@"):
            # Resolve attributes (e.g. gml:id)
            if pos:
                return None  # invalid attribute

            xml_name = node_name[1:]
            attribute = self._find_attribute(xml_name=parse_qname(xml_name, ns_aliases))
            return [attribute] if attribute is not None else None
        else:
            element = self._find_element(xml_name=parse_qname(node_name, ns_aliases))
            if element is None:
                return None

            if pos:
                if not element.type.is_complex_type:
                    return None
                else:
                    # Recurse into the child node to find the next part
                    child_path = element.type.resolve_element_path(xpath[pos + 1 :], ns_aliases)
                    return [element] + child_path if child_path is not None else None
            else:
                return [element]

    def _find_element(self, xml_name: str) -> XsdElement | None:
        """Locate an element by name"""
        for element in self.elements:
            if element.xml_name == xml_name:
                return element

        # When there is a base class, resolve elements there too.
        if self.base is not None and self.base.is_complex_type:
            return self.base._find_element(xml_name)
        return None

    def _find_attribute(self, xml_name: str) -> XsdAttribute | None:
        """Locate an attribute by name"""
        for attribute in self.attributes:
            if attribute.xml_name == xml_name:
                return attribute

        # When there is a base class, resolve attributes there too.
        if self.base is not None and self.base.is_complex_type:
            return self.base._find_attribute(xml_name)
        return None


class ORMPath:
    """Base class to provide raw XPath results.

    This base class is designed to allow other query types (besides XPath) too,
    and allows inserting raw data directly to the query compiler (for unit testing).
    """

    def __init__(self, orm_path: str, orm_filters: Q | None = None, is_many=False):
        """Base constructor just assigns items.
        Overwritten classes likely replace this with properties.
        """
        self.orm_path = orm_path
        self.orm_filters = orm_filters
        self.is_many = is_many

    def __repr__(self):
        return (
            f"{self.__class__.__name__}(orm_path={self.orm_path!r}"
            f", orm_filters={self.orm_filters!r})"
        )

    def build_lhs(self, compiler: CompiledQuery):
        """Give the ORM part when this element is used as left-hand-side of a comparison.
        For example: ``path == value``.
        """
        if self.is_many:
            compiler.add_distinct()
        if self.orm_filters:
            compiler.add_extra_lookup(self.orm_filters)
        return self.orm_path

    def build_rhs(self, compiler: CompiledQuery):
        """Give the ORM part when this element would be used as right-hand-side.
        For example: ``path1 == path2`` or ``value == path``.
        """
        if self.is_many:
            compiler.add_distinct()
        return F(self.build_lhs(compiler))


class XPathMatch(ORMPath):
    """The ORM path result from am XPath query.

    This result object defines how to resolve an XPath to an ORM object.
    """

    #: The matched element, with all it's parents.
    nodes: list[XsdNode]

    #: The source XPath query
    query: str

    #: The additional filters are needed (due to [@attr=..] syntax).
    orm_filters: Q | None

    def __init__(self, feature_type: FeatureType, nodes: list[XsdNode], query: str):
        self.feature_type = feature_type
        self.nodes = nodes
        self.query = query
        self.orm_filters = None

        if "[" in self.query:
            # If there is an element[@attr=...]/field tag,
            # the build_...() logic should return a Q() object.
            raise NotImplementedError(f"Complex XPath queries are not supported yet: {self.query}")

    @property
    def orm_path(self) -> str:
        """Give the Django ORM path (field__relation__relation2) to the result."""
        return self.nodes[-1].orm_path

    def __iter__(self):
        return iter(self.nodes)

    def __getitem__(self, item) -> XsdNode:
        return self.nodes[item]

    def __repr__(self):
        return f"XPathMatch(nodes={self.nodes!r}, query={self.query!r})"

    @property
    def child(self) -> XsdNode:
        """Return only the final element"""
        return self.nodes[-1]

    @cached_property
    def is_many(self) -> bool:
        """Return whether this ORM path walks over an element that occurs multiple times"""
        return any(node.is_many for node in self.nodes)

    def build_lhs(self, compiler: CompiledQuery):
        """Give the ORM part when this element is used as left-hand-side of a comparison.
        For example: ``path == value``.
        """
        if self.is_many:
            compiler.add_distinct()
        if self.orm_filters:
            compiler.add_extra_lookup(self.orm_filters)
        return self.child.build_lhs_part(compiler, self)

    def build_rhs(self, compiler: CompiledQuery):
        """Give the ORM part when this element would be used as right-hand-side.
        For example: ``path1 == path2`` or ``value == path``.
        """
        if self.is_many:
            compiler.add_distinct()
        if self.orm_filters:
            compiler.add_extra_lookup(self.orm_filters)
        return self.child.build_rhs_part(compiler, self)


if TYPE_CHECKING:
    from .features import FeatureType
    from .parsers.query import CompiledQuery
