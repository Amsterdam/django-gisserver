from typing import List

from gisserver.features import FeatureType
from gisserver.operations.base import WFSMethod
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

    def render_feature_type(self, feature_type):
        output = StringBuffer()
        class_name = f"{feature_type.name}Type"

        # This declares the that the <app:featureName> is a class of a type.
        output.write(
            f'  <element name="{feature_type.name}"'
            f' type="app:{class_name}" substitutionGroup="gml:AbstractFeature" />\n\n'
        )

        # Next, the complexType is rendered that defines the element contents.
        # The type is declared as subclass of <gml:AbstractFeatureType>,
        # which allows child elements like <gml:name> and <gml:boundedBy>.
        output.write(
            f'  <complexType name="{class_name}">\n'
            "    <complexContent>\n"
            '      <extension base="gml:AbstractFeatureType">\n'
            "        <sequence>\n"
        )

        for xsd_element in feature_type.xsd_fields:
            output.write(f"          {xsd_element}\n")

        output.write(
            "        </sequence>\n"
            "      </extension>\n"
            "    </complexContent>\n"
            "  </complexType>\n"
        )
        return output.getvalue()
