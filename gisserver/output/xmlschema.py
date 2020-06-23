from collections import deque

from typing import List

from gisserver.features import FeatureType
from gisserver.operations.base import WFSMethod
from gisserver.types import XsdComplexType
from .base import OutputRenderer, StringBuffer


class XMLSchemaRenderer(OutputRenderer):
    """Output rendering for DescribeFeatureType.

    This renders a valid XSD schema that describes the data type of the feature.
    """

    content_type = "application/gml+xml; version=3.2"  # mandatory for WFS

    def __init__(self, method: WFSMethod, feature_types: List[FeatureType]):
        """Overwritten method to handle the DescribeFeatureType context."""
        self.server_url = method.view.server_url
        self.app_xml_namespace = method.view.xml_namespace
        self.feature_types = feature_types

    def render_stream(self):
        output = StringBuffer()
        output.write(
            f"""<?xml version='1.0' encoding="UTF-8" ?>
<schema
   xmlns="http://www.w3.org/2001/XMLSchema"
   xmlns:app="{self.app_xml_namespace}"
   xmlns:gml="http://www.opengis.net/gml/3.2"
   targetNamespace="{self.app_xml_namespace}"
   elementFormDefault="qualified" version="0.1">

"""
        )
        output.write(self.render_imports())
        output.write("\n")

        for feature_type in self.feature_types:
            output.write(self.render_feature_type(feature_type))

        output.write("</schema>\n")
        return output.getvalue()

    def render_imports(self):
        return (
            '  <import namespace="http://www.opengis.net/gml/3.2"'
            ' schemaLocation="http://schemas.opengis.net/gml/3.2.1/gml.xsd" />\n'
        )

    def render_feature_type(self, feature_type: FeatureType):
        output = StringBuffer()
        xsd_type: XsdComplexType = feature_type.xsd_type

        # This declares the that a top-level <app:featureName> is a class of a type.
        output.write(
            f'  <element name="{feature_type.name}"'
            f' type="{xsd_type}" substitutionGroup="gml:AbstractFeature" />\n\n'
        )

        # Next, the complexType is rendered that defines the element contents.
        # Next, the complexType(s) are rendered that defines the element contents.
        # In case any fields are expanded (hence become sub-types), these are also included.
        output.write(self.render_complex_type(xsd_type))
        for complex_type in self._get_complex_types(xsd_type):
            output.write(self.render_complex_type(complex_type))

        return output.getvalue()

    def render_complex_type(self, complex_type: XsdComplexType):
        """Write the definition of a single class."""
        class_name = complex_type.name
        if class_name.startswith("app:"):
            # This might not be the official XML way (this should compare namespace URI's)
            # but for now this is good enough. Since "app" is our targetNamespace, this
            # prefix can be removed.
            class_name = class_name[4:]

        output = StringBuffer()
        output.write(
            f'  <complexType name="{class_name}">\n'
            "    <complexContent>\n"
            f'      <extension base="{complex_type.base}">\n'
            "        <sequence>\n"
        )

        for xsd_element in complex_type.elements:
            output.write(f"          {xsd_element}\n")

        output.write(
            "        </sequence>\n"
            "      </extension>\n"
            "    </complexContent>\n"
            "  </complexType>\n\n"
        )
        return output.getvalue()

    def _get_complex_types(self, root: XsdComplexType) -> List[XsdComplexType]:
        """Find which fields of the XSDElements reference to complex types."""
        worklist = deque(root.elements)
        complex_types = {}

        # Walk through next types, unless they are already seen.
        # No recursion is used here to handle circular loops of types.
        while worklist:
            element = worklist.popleft()
            element_type = element.type
            if element_type.is_complex_type and element_type.name not in complex_types:
                # ComplexType was not seen before, register it.
                # It's members are added to the worklist.
                complex_types[element_type.name] = element_type
                worklist.extend(element_type.elements)

        # Present in a consistent order
        return complex_types.values()
