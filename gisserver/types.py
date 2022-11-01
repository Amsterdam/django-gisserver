"""Internal XSD type definitions.

These types are the internal schema definition on which all output is generated.

The end-users of this library typically create a WFS feature type definition by using
the :class:~gisserver.features.FeatureType` / :class:`~gisserver.features.FeatureField` classes.

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

import operator
import re
from dataclasses import dataclass, field
from decimal import Decimal as D
from enum import Enum
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.gis.db.models import F, GeometryField
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.fields.related import (  # Django 2 imports
    ForeignObjectRel,
    RelatedField,
)
from django.utils import dateparse
from django.utils.functional import cached_property

from gisserver.exceptions import ExternalParsingError, OperationProcessingFailed
from gisserver.geometries import CRS, WGS84  # noqa: F401 / for backwards compatibility

try:
    from typing import Literal  # Python 3.8

    _unbounded = Literal["unbounded"]
except ImportError:
    _unbounded = str

if "django.contrib.postgres" in settings.INSTALLED_APPS:
    from django.contrib.postgres.fields import ArrayField
else:
    ArrayField = None

__all__ = [
    "ORMPath",
    "XPathMatch",
    "XsdAnyType",
    "XsdAttribute",
    "XsdComplexType",
    "XsdElement",
    "XsdNode",
    "XsdTypes",
    "split_xml_name",
    "FES20",
    "GML21",
    "GML32",
    "XSI",
]

GML21 = "http://www.opengis.net/gml"
GML32 = "http://www.opengis.net/gml/3.2"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
FES20 = "http://www.opengis.net/fes/2.0"

RE_XPATH_ATTR = re.compile(r"\[[^\]]+\]$")  # match [@attr=..]
TYPES_TO_PYTHON = {}


class XsdAnyType:
    """Base class for all types used in the XML definition"""

    name: str
    prefix = None
    is_complex_type = False
    is_geometry = False

    def __str__(self):
        """Return the type name"""
        raise NotImplementedError()

    def with_prefix(self, prefix="xs"):
        xml_name = str(self)
        if ":" in xml_name:
            return xml_name
        else:
            return f"{prefix}:{xml_name}"

    def to_python(self, raw_value):
        """Convert a raw string value to this type representation"""
        return raw_value


class XsdTypes(XsdAnyType, Enum):
    """Brief enumeration of basic XMLSchema types.

    The :class:`XsdElement` and :class:`XsdAttribute` can use these enum members
    to indicate their value is a well-known XML Schema. Some GML types are included as well.

    The default namespace is the "xs:" (XMLSchema).
    Based on https://www.w3.org/TR/xmlschema-2/#built-in-datatypes
    """

    anyType = "anyType"  # Needs to be anyType, as "xsd:any" is an element, not a type.
    string = "string"
    boolean = "boolean"
    decimal = "decimal"  # the base type for all numbers too.
    integer = "integer"  # integer value
    float = "float"
    double = "double"
    time = "time"
    date = "date"
    dateTime = "dateTime"
    anyURI = "anyURI"

    # Number variations
    byte = "byte"  # signed 8-bit integer
    short = "short"  # signed 16-bit integer
    int = "int"  # signed 32-bit integer
    long = "long"  # signed 64-bit integer
    unsignedByte = "unsignedByte"  # unsigned 8-bit integer
    unsignedShort = "unsignedShort"  # unsigned 16-bit integer
    unsignedInt = "unsignedInt"  # unsigned 32-bit integer
    unsignedLong = "unsignedLong"  # unsigned 64-bit integer

    # Less common, but useful nonetheless:
    duration = "duration"
    nonNegativeInteger = "nonNegativeInteger"
    gYear = "gYear"
    hexBinary = "hexBinary"
    base64Binary = "base64Binary"
    token = "token"
    language = "language"

    # Types that contain a GML value as member:
    gmlGeometryPropertyType = "gml:GeometryPropertyType"
    gmlPointPropertyType = "gml:PointPropertyType"
    gmlCurvePropertyType = "gml:CurvePropertyType"  # curve is base for LineString
    gmlSurfacePropertyType = "gml:SurfacePropertyType"  # GML2 had PolygonPropertyType
    gmlMultiSurfacePropertyType = "gml:MultiSurfacePropertyType"
    gmlMultiPointPropertyType = "gml:MultiPointPropertyType"
    gmlMultiCurvePropertyType = "gml:MultiCurvePropertyType"
    gmlMultiGeometryPropertyType = "gml:MultiGeometryPropertyType"

    # Other typical GML values
    gmlCodeType = "gml:CodeType"  # for <gml:name>
    gmlBoundingShapeType = "gml:BoundingShapeType"  # for <gml:boundedBy>

    #: A direct geometry value (used as function argument type)
    gmlAbstractGeometryType = "gml:AbstractGeometryType"

    #: A feature that has an gml:name and gml:boundedBy as possible child element.
    gmlAbstractFeatureType = "gml:AbstractFeatureType"
    gmlAbstractGMLType = "gml:AbstractGMLType"  # base class of gml:AbstractFeatureType

    def __str__(self):
        return self.value

    @property
    def prefix(self) -> str | None:
        """Extrapolate the prefix from the type name"""
        xml_name = str(self)
        colon = xml_name.find(":")
        return xml_name[:colon] if colon else None

    @cached_property
    def is_geometry(self):
        """Whether the value represents a element which contains a GML element."""
        return self.prefix == "gml" and self.value.endswith("PropertyType")

    @cached_property
    def _to_python_func(self):
        if not TYPES_TO_PYTHON:
            _init_types_to_python()

        try:
            return TYPES_TO_PYTHON[self]
        except KeyError:
            raise NotImplementedError(
                f'Casting to "{self}" is not implemented.'
            ) from None

    def to_python(self, raw_value):
        """Convert a raw string value to this type representation"""
        if self.is_geometry:
            # Leave complex values as-is.
            return raw_value

        try:
            return self._to_python_func(raw_value)
        except ExternalParsingError:
            raise  # subclass of ValueError so explicitly caught and reraised
        except (TypeError, ValueError, ArithmeticError) as e:
            # ArithmeticError is base of DecimalException
            raise ExternalParsingError(f"Can't cast '{raw_value}' to {self}.") from e


def _init_types_to_python():
    """Define how well-known scalar types are parsed into python
    (mimicking Django's to_python()):
    """
    global TYPES_TO_PYTHON
    from gisserver.parsers import values  # avoid cyclic import

    as_is = lambda v: v
    TYPES_TO_PYTHON = {
        XsdTypes.date: dateparse.parse_date,
        XsdTypes.dateTime: values.parse_iso_datetime,
        XsdTypes.time: dateparse.parse_time,
        XsdTypes.string: as_is,
        XsdTypes.boolean: values.parse_bool,
        XsdTypes.integer: int,
        XsdTypes.int: int,
        XsdTypes.long: int,
        XsdTypes.short: int,
        XsdTypes.byte: int,
        XsdTypes.unsignedInt: int,
        XsdTypes.unsignedLong: int,
        XsdTypes.unsignedShort: int,
        XsdTypes.unsignedByte: int,
        XsdTypes.float: D,
        XsdTypes.double: D,
        XsdTypes.decimal: D,
        XsdTypes.gmlCodeType: as_is,
        XsdTypes.anyType: values.auto_cast,
    }


class XsdNode:
    """Base class for :class:`XsdElement` and :class:`XsdAttribute`.

    This contains all common mapping/resolving that both elements and attributes share.
    For instance, how XML nodes are mapped into ORM paths, converted into ORM filters,
    parse query input and read model attributes to write as output.
    """

    is_attribute = False
    is_many = False

    name: str
    type: XsdAnyType  # Both XsdComplexType and XsdType are allowed
    prefix: str | None

    #: Which field to read from the model to get the value
    #: This supports dot notation to access related attributes.
    source: models.Field | ForeignObjectRel | None

    #: Which field to read from the model to get the value
    #: This supports dot notation to access related attributes.
    model_attribute: str | None

    def __init__(
        self,
        name: str,
        type: XsdAnyType,
        *,
        prefix: str | None = "app",
        source: models.Field | ForeignObjectRel | None = None,
        model_attribute: str | None = None,
    ):
        # Using plain assignment instead of dataclass turns out to be needed
        # for flexibility and easier subclassing.
        self.name = name
        self.type = type
        self.prefix = prefix
        self.source = source
        self.model_attribute = model_attribute or self.name

        if ":" in self.name:
            raise ValueError("Use 'prefix' argument for namespaces")

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
        field: models.Field | ForeignObjectRel | None,
    ):
        """Select the most efficient read function to retrieves the value."""
        if field is None:
            # No model field, can only use getattr(). The attrgetter function has
            # built-in support for traversing model attributes with dots.
            return operator.attrgetter(model_attribute)
        elif isinstance(field, ForeignObjectRel):
            # Special handling, has no value_from_object()
            return operator.attrgetter(model_attribute)
        elif "." not in model_attribute:
            # Shortcut, can just use Django's value_from_object.
            # This allows Django fields to override the object retrieval.
            # Not using value_to_string() as different output formats may serialize differently.
            return field.value_from_object
        else:
            # Need to traverse foreign key relations before using value_from_objec().
            names = model_attribute.split(".")

            def _related_get_value_from_object(instance):
                for name in names[:-1]:
                    instance = getattr(instance, name)
                return field.value_from_object(instance)

            return _related_get_value_from_object

    @cached_property
    def is_geometry(self) -> bool:
        """Tell whether the XML node/element should be handed as GML geometry."""
        return self.type.is_geometry or isinstance(self.source, GeometryField)

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
        return f"{self.prefix}:{self.name}" if self.prefix else self.name

    @cached_property
    def orm_path(self) -> str:
        """The ORM field lookup to perform."""
        if self.model_attribute is None:
            raise ValueError(f"Node {self.xml_name} has no 'model_attribute' set.")
        return self.model_attribute.replace(".", "__")

    @cached_property
    def orm_field(self) -> str:
        """The direct ORM field that provides this property."""
        if self.model_attribute is None:
            raise ValueError(f"Node {self.xml_name} has no 'model_attribute' set.")
        return self.model_attribute.split(".", 1)[0]

    @cached_property
    def orm_relation(self) -> tuple[str | None, str]:
        """The ORM field and parent relation"""
        if self.model_attribute is None:
            raise ValueError(f"Node {self.xml_name} has no 'model_attribute' set.")

        try:
            path, field = self.model_attribute.rsplit(".", 1)
        except ValueError:
            return None, self.model_attribute
        else:
            return path.replace(".", "__"), field

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
                return value
            else:
                # Support value_from_object() on custom fields.
                return self.format_value(self._valuegetter(instance))
        except (AttributeError, ObjectDoesNotExist):
            # E.g. Django foreign keys that point to a non-existing member.
            return None

    def format_value(self, value):
        """Allow to apply some final transformations on a value.
        This is mainly used to support @gml:id which includes a prefix.
        """
        return value

    @cached_property
    def _form_field(self):
        """Internal cached field for to_python()"""
        return self.source.formfield()

    def to_python(self, raw_value: str):
        """Convert a raw value to the Python data type for this element type."""
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
            raise ValidationError(
                f"Invalid data for the '{self.name}' property: {e}"
            ) from e

        return raw_value

    def validate_comparison(self, raw_value: str, lookup, tag=None):
        """Validate whether the input value can be used in a comparison.
        This avoids comparing a database DATETIME object to an integer.

        The raw string value can be passed here. Auto-cased values could
        raise an TypeError due to being unsupported by the validation.
        """
        if self.source is not None:
            # Not calling self.source.validate() as that checks for allowed choices,
            # which shouldn't be checked against for a filter query.
            raw_value = self.to_python(raw_value)

            # Check whether the Django model field supports the lookup
            # This prevents calling LIKE on a datetime or float field.
            # For foreign keys, this depends on the target field type.
            if self.source.get_lookup(lookup) is None or (
                isinstance(self.source, RelatedField)
                and self.source.target_field.get_lookup(lookup) is None
            ):
                raise OperationProcessingFailed(
                    "filter",
                    f"Operator '{tag}' is not supported for the '{self.name}' property.",
                    status_code=400,  # not HTTP 500 here. Spec allows both.
                )

        return raw_value


class XsdElement(XsdNode):
    """Declare an XSD element.

    Typically, this maps into a Django model field.

    This holds the definition for a single property in the WFS server.
    It's used in ``DescribeFeatureType`` to output the field metadata,
    and used in ``GetFeature`` to access the actual value from the object.
    Overriding :meth:`get_value` allows to override this logic.

    The :attr:`name` may differ from the underlying :attr:`model_attribute`,
    so the WFS server can use other field names then the underlying model.

    A dotted-path notation can be used for :attr:`model_attribute` to access
    a related field. For the WFS client, the data appears to be flattened.
    """

    nillable: bool | None
    min_occurs: int | None
    max_occurs: int | None

    def __init__(
        self,
        name: str,
        type: XsdAnyType,
        *,
        prefix: str | None = "app",
        nillable: bool | None = None,
        min_occurs: int | None = None,
        max_occurs: int | _unbounded | None = None,
        source: models.Field | ForeignObjectRel | None = None,
        model_attribute: str | None = None,
    ):
        super().__init__(
            name, type, prefix=prefix, source=source, model_attribute=model_attribute
        )
        self.nillable = nillable
        self.min_occurs = min_occurs
        self.max_occurs = max_occurs

    @cached_property
    def as_xml(self):
        attributes = [f'name="{self.name}" type="{self.type}"']
        if self.min_occurs is not None:
            attributes.append(f'minOccurs="{self.min_occurs}"')
        if self.max_occurs is not None:
            attributes.append(f'maxOccurs="{self.max_occurs}"')
        if self.nillable:
            str_bool = "true" if self.nillable else "false"
            attributes.append(f'nillable="{str_bool}"')

        return "<element {} />".format(" ".join(attributes))

    def __str__(self):
        return self.as_xml

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
        prefix: str | None = "app",
        use: str = "optional",
        source: models.Field | ForeignObjectRel | None = None,
        model_attribute: str | None = None,
    ):
        super().__init__(
            name, type, prefix=prefix, source=source, model_attribute=model_attribute
        )
        self.use = use


class GmlIdAttribute(XsdAttribute):
    """A virtual 'gml:id' attribute that can be queried.
    This subclass has overwritten get_value() logic to format the value.
    """

    type_name: str

    def __init__(
        self,
        type_name: str,
        source: models.Field | ForeignObjectRel | None = None,
        model_attribute="pk",
    ):
        super().__init__(
            prefix="gml", name="id", source=source, model_attribute=model_attribute
        )
        object.__setattr__(self, "type_name", type_name)

    def get_value(self, instance: models.Model):
        pk = super().get_value(instance)  # handle dotted-name notations
        return f"{self.type_name}.{pk}"

    def format_value(self, value):
        """Format the value as retrieved from the database."""
        return f"{self.type_name}.{value}"


class GmlNameElement(XsdElement):
    """A subclass to handle the <gml:name> element.
    This displays a human-readable title for the object.

    Currently, this just reads a single attribute,
    but it can be extended to support formatted names
    (although that would make comparisons on ``element@gml:name`` more complex).
    """

    def __init__(
        self,
        model_attribute: str,
        source: models.Field | ForeignObjectRel | None = None,
        feature_type=None,
    ):
        # Prefill most known fields
        super().__init__(
            prefix="gml",
            name="name",
            type=XsdTypes.gmlCodeType,
            min_occurs=0,
            source=source,
            model_attribute=model_attribute,
        )
        self.feature_type = feature_type

    def get_value(self, instance: models.Model):
        """Override value retrieval to retrieve the value from the feature type."""
        if self.feature_type is not None:
            # Let FeatureType provide a nice display/title for the object.
            return self.feature_type.get_display_value(instance)
        else:
            # Fallback, when using this class at a sub-level object.
            return super().get_value(instance)


class GmlBoundedByElement(XsdElement):
    """A subclass to handle the <gml:boundedBy> element.

    This override makes sure this non-model element data
    can be included in the XML tree like every other element.
    Its value is the complete bounding box of the feature type data.
    """

    is_geometry = True  # Override type

    def __init__(self, feature_type):
        # Prefill most known fields
        super().__init__(
            prefix="gml",
            name="boundedBy",
            type=XsdTypes.gmlBoundingShapeType,
            min_occurs=0,
        )
        self.feature_type = feature_type
        self.model_attribute = None

    def build_lhs_part(self, compiler: CompiledQuery, match: ORMPath):
        """Give the ORM part when this element is used as
        left-hand-side of a comparison."""
        return compiler.add_annotation(self.build_rhs_part(compiler, match))

    def build_rhs_part(self, compiler: CompiledQuery, match: ORMPath):
        """Give the ORM part when this element would be used as right-hand-side"""
        raise NotImplementedError("queries against <gml:boundedBy> are not supported")

    def get_value(self, instance: models.Model, crs: CRS | None = None):
        """Provide the value of the <gml:boundedBy> field
        (if this is not given by the database already)."""
        return self.feature_type.get_envelope(instance, crs=crs)


@dataclass(frozen=True)
class XsdComplexType(XsdAnyType):
    """Define an <xsd:complexType> that represents a whole class definition.

    Typically, this maps into a Django model, with each element pointing to a model field.

    The complex can hold multiple :class:`XsdElement` and :class:`XsdAttribute`
    nodes as children, composing an object. The elements themselves can point
    to a complex type themselves, to create a nested class structure.
    That also allows embedding models with their relations into a single response.

    This object definition is the internal "source of truth" regarding
    which field names and field elements are used in the WFS server.
    The ``DescribeFeatureType`` request uses this definition to render the matching XMLSchema.
    Incoming XPath queries are parsed using this object to resolve the XPath to model attributes.

    Objects of this type are typically generated by the ``FeatureType`` and
    ``ComplexFeatureField`` classes, using the Django model data.

    By default, The type is declared as subclass of <gml:AbstractFeatureType>,
    which allows child elements like <gml:name> and <gml:boundedBy>.
    """

    #: Internal class name (without XML prefix)
    name: str

    #: All elements in this class
    elements: list[XsdElement]

    #: All attributes in this class
    attributes: list[XsdAttribute] = field(default_factory=list)

    #: The base class of this type. Typically gml:AbstractFeatureType,
    #: which provides the <gml:name> and <gml:boundedBy> elements.
    base: XsdAnyType = XsdTypes.gmlAbstractFeatureType

    #: The prefix alias to use for the namespace.
    prefix: str = "app"

    #: The Django model class that this type was based on.
    source: type[models.Model] | None = None

    def __str__(self):
        return self.xml_name

    @cached_property
    def xml_name(self):
        """Name in the XMLSchema (e.g. app:SomeClass)."""
        return f"{self.prefix}:{self.name}"

    @property
    def is_complex_type(self):
        return True  # a property to avoid being used as field.

    @cached_property
    def geometry_elements(self) -> list[XsdElement]:
        """Shortcut to get all geometry elements"""
        return [e for e in self.elements if e.is_geometry]

    @cached_property
    def complex_elements(self) -> list[_XsdElement_WithComplexType]:
        """Shortcut to get all elements with a complex type"""
        return [e for e in self.elements if e.type.is_complex_type]

    @cached_property
    def flattened_elements(self) -> list[XsdElement]:
        """Shortcut to get all elements with a flattened model attribite"""
        return [e for e in self.elements if e.is_flattened]

    def resolve_element_path(self, xpath: str) -> list[XsdNode] | None:
        """Resolve a xpath reference to the actual node.
        This returns the whole path, including in-between relations, if a match was found.

        This is used by :meth:`~gisserver.features.FeatureType.resolve_element`
        to convert a request XPath element into the ORM attributes for database queries.
        """
        try:
            pos = xpath.rindex("/")
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

            # Remove app: prefixes, or any alias of it (see explanation below)
            xml_name = node_name[1:]
            attribute = self._find_attribute(xml_name=xml_name)
            return [attribute] if attribute is not None else None
        else:
            element = self._find_element(node_name)
            if element is None:
                return None

            if pos:
                if not element.type.is_complex_type:
                    return None
                else:
                    # Recurse into the child node to find the next part
                    child_path = element.type.resolve_element_path(xpath[pos + 1 :])
                    return [element] + child_path if child_path is not None else None
            else:
                return [element]

    def _find_element(self, xml_name) -> XsdElement | None:
        """Locate an element by name"""
        for element in self.elements:
            if element.xml_name == xml_name:
                return element

        prefix, name = split_xml_name(xml_name)
        if prefix != "gml" and prefix != self.prefix:
            # Ignore current app namespace. Note this should actually compare the
            # xmlns URI's, but this will suffice for now. The ElementTree parser
            # doesn't provide access to 'xmlns' definitions on the element (or it's
            # parents), so a tag like this is essentially not parsable for us:
            # <ValueReference xmlns:tns="http://...">tns:fieldname</ValueReference>
            for element in self.elements:
                if element.name == name:
                    return element

        # When there is a base class, resolve elements there too.
        if self.base.is_complex_type:
            return self.base._find_element(xml_name)
        return None

    def _find_attribute(self, xml_name) -> XsdAttribute | None:
        """Locate an attribute by name"""
        for attribute in self.attributes:
            if attribute.xml_name == xml_name:
                return attribute

        prefix, name = split_xml_name(xml_name)
        if prefix != "gml" and prefix != self.prefix:
            # Allow any namespace to match, since the stdlib ElementTree parser
            # can't resolve namespaces at all.
            for attribute in self.attributes:
                if attribute.name == name:
                    return attribute

        # When there is a base class, resolve attributes there too.
        if self.base.is_complex_type:
            return self.base._find_attribute(xml_name)
        return None


def split_xml_name(xml_name: str) -> tuple[str | None, str]:
    """Remove the namespace prefix from an element."""
    try:
        prefix, name = xml_name.split(":", 1)
        return prefix, name
    except ValueError:
        return None, xml_name


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
        For example: "path == value".
        """
        if self.is_many:
            compiler.add_distinct()
        if self.orm_filters:
            compiler.add_extra_lookup(self.orm_filters)
        return self.orm_path

    def build_rhs(self, compiler: CompiledQuery):
        """Give the ORM part when this element would be used as right-hand-side.
        For example: "path == path" or "value == path".
        """
        if self.is_many:
            compiler.add_distinct()
        return F(self.build_lhs(compiler))


class XPathMatch(ORMPath):
    """The ORM path result from am XPath query.

    This result object defines how to resolve an XPath to a ORM object.
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
            raise NotImplementedError(
                f"Complex XPath queries are not supported yet: {self.query}"
            )

    @cached_property
    def orm_path(self) -> str:
        """Give the Django ORM path (field__relation__relation2) to the result."""
        return "__".join(xsd_node.orm_path for xsd_node in self.nodes)

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
        """Delegate the LHS construction to the final XsdNode."""
        if self.is_many:
            compiler.add_distinct()
        if self.orm_filters:
            compiler.add_extra_lookup(self.orm_filters)
        return self.child.build_lhs_part(compiler, self)

    def build_rhs(self, compiler: CompiledQuery):
        """Delegate the RHS construction to the final XsdNode."""
        if self.is_many:
            compiler.add_distinct()
        if self.orm_filters:
            compiler.add_extra_lookup(self.orm_filters)
        return self.child.build_rhs_part(compiler, self)


if TYPE_CHECKING:
    from .features import FeatureType
    from .parsers.fes20 import CompiledQuery
