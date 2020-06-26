"""Internal XSD type definitions.

These types are the internal definition on which all output is generated.
It's constructed from the model metadata by the `FeatureType` / `FeatureField`
classes. Custom field types could also generate these field types.
"""
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Type

from django.contrib.gis.db.models import GeometryField
from django.db import models
from django.utils.functional import cached_property

from gisserver.geometries import CRS, WGS84  # noqa, for backwards compatibility

__all__ = [
    "XsdAnyType",
    "XsdTypes",
    "XsdComplexType",
]

RE_XPATH_ATTR = re.compile(r"\[[^\]]+\]$")


class XsdAnyType:
    """Base class for all types used in the XML definition"""

    prefix = None
    is_complex_type = False

    def __str__(self):
        raise NotImplementedError()

    def with_prefix(self, prefix="xs"):
        raise NotImplementedError()


class XsdTypes(XsdAnyType, Enum):
    """Brief enumeration of basic XSD-types.

    The default namespace is the "xs:" (XMLSchema).
    Based on https://www.w3.org/TR/xmlschema-2/#built-in-datatypes
    """

    anyType = "anyType"  # Needs to be anyType, as "xsd:any" is an element, not a type.
    string = "string"
    boolean = "boolean"
    decimal = "decimal"  # the base type for all numbers too.
    integer = "integer"
    float = "float"
    double = "double"
    time = "time"
    date = "date"
    dateTime = "dateTime"
    anyURI = "anyURI"

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

    #: A direct geometry value
    gmlAbstractGeometryType = "gml:AbstractGeometryType"

    #: A feature that has an gml:name and gml:boundedBy as posible child element.
    gmlAbstractFeatureType = "gml:AbstractFeatureType"

    def __str__(self):
        return self.value

    @property
    def prefix(self) -> Optional[str]:
        colon = self.value.find(":")
        return self.value[:colon] if colon else None

    def with_prefix(self, prefix="xs"):
        if ":" in self.value:
            return self.value
        else:
            return f"{prefix}:{self.value}"


@dataclass(frozen=True)
class XsdElement:
    """Declare an XSD element"""

    name: str
    type: XsdAnyType  # Both XsdComplexType and XsdType are allowed
    nillable: Optional[bool] = None
    min_occurs: Optional[int] = None
    max_occurs: Optional[int] = None
    source: Optional[models.Field] = None

    #: Which field to read from the model to get the value
    model_attribute: Optional[str] = None

    def __post_init__(self):
        if self.model_attribute is None:
            object.__setattr__(self, "model_attribute", self.name)

    @cached_property
    def is_gml(self):
        return isinstance(self.source, GeometryField) or self.type.prefix == "gml"

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

    def get_value(self, instance: models.Model):
        """Provide the value for the """
        # For foreign keys, it's not possible to use the model value,
        # as that would conflict with the field type in the XSD schema.
        try:
            return getattr(instance, self.model_attribute)
        except AttributeError:
            # E.g. Django foreign keys that point to a non-existing member.
            return None


@dataclass(frozen=True)
class XsdComplexType(XsdAnyType):
    """Define an <xsd:complexType> that represents a whole class definition.

    By default, The type is declared as subclass of <gml:AbstractFeatureType>,
    which allows child elements like <gml:name> and <gml:boundedBy>.
    """

    name: str
    elements: List[XsdElement]
    base: XsdTypes = XsdTypes.gmlAbstractFeatureType
    source: Optional[Type[models.Model]] = None

    def __str__(self):
        return f"{self.prefix}:{self.name}"

    @property
    def is_complex_type(self):
        return True

    @property
    def prefix(self):
        # mimic API of XsdTypes
        return "app"

    def with_prefix(self, prefix="xs"):
        # mimic API of XsdTypes
        return str(self)

    @cached_property
    def gml_elements(self) -> List[XsdElement]:
        """Shortcut to get all geometry elements"""
        return [e for e in self.elements if e.is_gml]

    @cached_property
    def complex_elements(self) -> List[XsdElement]:
        """Shortcut to get all elements with a complex type"""
        return [e for e in self.elements if e.type.is_complex_type]

    def resolve_element_path(self, xpath: str) -> Optional[List[XsdElement]]:
        """Resolve an xpath reference to the actual node.
        This returns the list of all levels if a match was found.
        """
        try:
            pos = xpath.rindex("/")
            node_name = xpath[:pos]
        except ValueError:
            node_name = xpath
            pos = 0

        # Strip any [@attr=..] conditions
        node_name = RE_XPATH_ATTR.sub("", node_name)

        for element in self.elements:
            if element.name == node_name:
                if pos:
                    if not element.type.is_complex_type:
                        return None
                    else:
                        child_path = element.type.resolve_element_path(xpath[pos + 1 :])
                        if child_path is None:
                            return None
                        else:
                            return [element] + child_path
                else:
                    return [element]

        return None
