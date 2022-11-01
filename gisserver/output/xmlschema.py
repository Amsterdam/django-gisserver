from __future__ import annotations

from collections import deque
from typing import Iterable, cast

from gisserver.features import FeatureType
from gisserver.operations.base import WFSMethod
from gisserver.types import XsdComplexType

from .base import OutputRenderer
from .buffer import StringBuffer


class XMLSchemaRenderer(OutputRenderer):
    """Output rendering for DescribeFeatureType.

    This renders a valid XSD schema that describes the data type of the feature.
    """

    content_type = "application/gml+xml; version=3.2"  # mandatory for WFS

    def __init__(self, method: WFSMethod, feature_types: list[FeatureType]):
        """Overwritten method to handle the DescribeFeatureType context."""
        self.server_url = method.view.server_url
        self.app_xml_namespace = method.view.xml_namespace
        self.feature_types = feature_types

    def render_stream(self):
        # For now, all features have the same XML namespace despite allowing
        # the prefixes to be different.
        xmlns_features = "\n   ".join(
            f'xmlns:{p}="{self.app_xml_namespace}"'
            for p in sorted(
                {feature_type.xml_prefix for feature_type in self.feature_types}
            )
        )

        output = StringBuffer()
        output.write(
            f"""<?xml version='1.0' encoding="UTF-8" ?>
<schema
   xmlns="http://www.w3.org/2001/XMLSchema"
   {xmlns_features}
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
        output = StringBuffer()
        output.write(
            f'  <complexType name="{complex_type.name}">\n'
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
