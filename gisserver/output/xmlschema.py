from __future__ import annotations

import typing
from collections import deque
from collections.abc import Iterable
from io import StringIO
from typing import cast

from gisserver.features import FeatureType
from gisserver.parsers.xml import xmlns
from gisserver.types import XsdComplexType, XsdElement

from .base import OutputRenderer
from .utils import to_qname

if typing.TYPE_CHECKING:
    from gisserver.operations.base import WFSMethod


class XMLSchemaRenderer(OutputRenderer):
    """Output rendering for DescribeFeatureType.

    This renders a valid XSD schema that describes the data type of the feature.
    """

    content_type = "application/gml+xml; version=3.2"  # mandatory for WFS
    xml_namespaces = {
        # Default extra namespaces to include in the xmlns="..." attributes
        "http://www.w3.org/2001/XMLSchema": "",  # no xs:string, but "string"
        "http://www.opengis.net/gml/3.2": "gml",
    }

    def __init__(self, method: WFSMethod, feature_types: list[FeatureType]):
        """Overwritten method to handle the DescribeFeatureType context."""
        super().__init__(method)
        self.feature_types = feature_types

        # For rendering type="..." fields, avoid xs: prefix.
        self.type_namespaces = self.app_namespaces.copy()
        self.type_namespaces[xmlns.xs.value] = ""  # no "xs:string" but "string"

    def render_stream(self):
        xmlns_attrib = self.render_xmlns_attributes(self.app_namespaces)

        # Allow targetNamespace to be unprefixed by self.to_qname().
        target_namespace = self.feature_types[0].xml_namespace
        self.app_namespaces[target_namespace] = ""  # no "app:element" but "element"

        self.output = output = StringIO()
        output.write(
            f"""<?xml version='1.0' encoding="UTF-8" ?>
<schema {xmlns_attrib}
   targetNamespace="{target_namespace}"
   elementFormDefault="qualified" version="0.1">

"""
        )
        output.write(self.render_imports())
        output.write("\n")

        for feature_type in self.feature_types:
            self.write_feature_type(feature_type)

        output.write("</schema>\n")
        return output.getvalue()

    def render_imports(self):
        return (
            '  <import namespace="http://www.opengis.net/gml/3.2"'
            ' schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd" />\n'
        )

    def write_feature_type(self, feature_type: FeatureType):
        xsd_type: XsdComplexType = feature_type.xsd_type

        # This declares the that a top-level <app:featureName> is a class of a type.
        xsd_type_qname = self.to_qname(xsd_type, self.type_namespaces)
        feature_qname = to_qname(
            feature_type.xml_namespace, feature_type.name, self.app_namespaces
        )
        self.output.write(
            f'  <element name="{feature_qname}"'
            f' type="{xsd_type_qname}" substitutionGroup="gml:AbstractFeature" />\n\n'
        )

        # Next, the complexType is rendered that defines the element contents.
        # Next, the complexType(s) are rendered that defines the element contents.
        # In case any fields are expanded (hence become subtypes), these are also included.
        self.write_complex_type(xsd_type)
        for complex_type in self._get_complex_types(xsd_type):
            self.write_complex_type(complex_type)

    def write_complex_type(self, complex_type: XsdComplexType):
        """Write the definition of a single class."""
        complex_qname = self.to_qname(complex_type)
        self.output.write(f'  <complexType name="{complex_qname}">\n    <complexContent>\n')
        if complex_type.base is not None:
            base_qname = self.to_qname(complex_type.base)
            self.output.write(f'      <extension base="{base_qname}">\n')

        self.output.write("        <sequence>\n")

        for xsd_element in complex_type.elements:
            self.output.write(f"          {self.render_element(xsd_element)}\n")

        self.output.write("        </sequence>\n")
        if complex_type.base is not None:
            self.output.write("      </extension>\n")
        self.output.write("    </complexContent>\n  </complexType>\n\n")

    def render_element(self, xsd_element: XsdElement):
        """Staticmethod for unit testing."""
        qname = self.to_qname(xsd_element)
        type_qname = self.to_qname(xsd_element.type, self.type_namespaces)

        attributes = [f'name="{qname}" type="{type_qname}"']
        if xsd_element.min_occurs is not None:
            attributes.append(f'minOccurs="{xsd_element.min_occurs}"')
        if xsd_element.max_occurs is not None:
            attributes.append(f'maxOccurs="{xsd_element.max_occurs}"')
        if xsd_element.nillable:
            str_bool = "true" if xsd_element.nillable else "false"
            attributes.append(f'nillable="{str_bool}"')

        return "<element {} />".format(" ".join(attributes))

    def _get_complex_types(self, root: XsdComplexType) -> Iterable[XsdComplexType]:
        """Find all fields that reference to complex types, including nested elements."""
        elements = deque(root.elements)
        complex_types = {}

        # Walk through next types, unless they are already seen.
        # No recursion is used here to handle circular loops of types.
        while elements:
            element = elements.popleft()
            element_type = element.type
            if element_type.is_complex_type and element_type.name not in complex_types:
                # ComplexType was not seen before, register it.
                # It's members are added to the deque for recursive processing.
                xsd_element_type = cast(XsdComplexType, element_type)
                complex_types[element_type.name] = xsd_element_type
                elements.extend(xsd_element_type.elements)

        # Present in a consistent order
        return complex_types.values()
