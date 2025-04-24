"""Outputting XML for the stored query logic."""

from __future__ import annotations

from io import StringIO
from xml.etree.ElementTree import Element, tostring

from gisserver.extensions.queries import QueryExpressionText, StoredQueryDescription
from gisserver.output.utils import attr_escape, tag_escape
from gisserver.parsers.xml import xmlns

from .base import XmlOutputRenderer


class ListStoredQueriesRenderer(XmlOutputRenderer):
    """Rendering for the ``<wfs:ListStoredQueriesResponse>``."""

    # XML Namespaces to include by default
    xml_namespaces = {
        xmlns.wfs20: "",
        xmlns.xs: "xs",
        xmlns.xsi: "xsi",
    }

    def __init__(self, operation, query_descriptions: list[StoredQueryDescription]):
        """Take the list of stored queries to render."""
        super().__init__(operation)
        self.all_feature_types = operation.view.get_bound_feature_types()
        self.query_descriptions = query_descriptions

    def render_stream(self):
        self.output = StringIO()
        self.output.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f"<ListStoredQueriesResponse"
            f" {self.render_xmlns_attributes()}"
            f' xsi:schemaLocation="http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd">\n'
        )
        for query_description in self.query_descriptions:
            self.write_query(query_description)

        self.output.write("</ListStoredQueriesResponse>\n")
        return self.output.getvalue()

    def write_query(self, query_description: StoredQueryDescription):
        self.output.write(
            f'  <StoredQuery id="{query_description.id}">\n'
            f"    <Title>{tag_escape(query_description.title)}</Title>\n"
        )

        for expression in query_description.expressions:
            return_types = expression.return_feature_types or self.all_feature_types
            for return_type in return_types:
                feature_qname = self.feature_to_qname(return_type)
                self.output.write(
                    f"    <ReturnFeatureType>{tag_escape(feature_qname)}</ReturnFeatureType>\n"
                )

        self.output.write("  </StoredQuery>\n")


class DescribeStoredQueriesRenderer(XmlOutputRenderer):
    """Rendering for the ``<wfs:DescribeStoredQueriesResponse>``."""

    # XML Namespaces to include by default
    xml_namespaces = {
        xmlns.wfs20: "",
        xmlns.xs: "xs",
        xmlns.xsi: "xsi",
    }

    def __init__(self, operation, query_descriptions: list[StoredQueryDescription]):
        """Take the list of stored queries to render."""
        super().__init__(operation)
        self.all_feature_types = operation.view.get_bound_feature_types()
        self.query_descriptions = query_descriptions

    def render_stream(self):
        self.output = StringIO()
        self.output.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f"<DescribeStoredQueriesResponse"
            f" {self.render_xmlns_attributes()}"
            f' xsi:schemaLocation="http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd">\n'
        )

        for query_description in self.query_descriptions:
            self.write_description(query_description)

        self.output.write("</DescribeStoredQueriesResponse>\n")
        return self.output.getvalue()

    def write_description(self, query_description: StoredQueryDescription):
        """Write the stored query description."""
        self.output.write(
            f'<StoredQueryDescription id="{attr_escape(query_description.id)}">\n'
            f"  <Title>{tag_escape(query_description.title)}</Title>\n"
            f"  <Abstract>{tag_escape(query_description.abstract)}</Abstract>\n"
        )

        # Declare parameters
        for name, xsd_type in query_description.parameters.items():
            type_qname = self.to_qname(xsd_type)
            self.output.write(f'  <Parameter name="{attr_escape(name)}" type="{type_qname}"/>\n')

        # The QueryExpressionText nodes allow code per return type.
        for expression in query_description.expressions:
            self.render_expression(expression)

        self.output.write("</StoredQueryDescription>\n")

    def render_expression(self, expression: QueryExpressionText):
        """Render the 'QueryExpressionText' node (no body content for now)."""
        is_private = "true" if expression.is_private else "false"
        if expression.return_feature_types is None:
            # for GetFeatureById
            types = " ".join(self.feature_to_qname(ft) for ft in self.all_feature_types)
        else:
            types = " ".join(
                self.feature_to_qname(return_type)
                for return_type in expression.return_feature_types
            )

        if expression.is_private or not expression.implementation_text:
            implementation_text = ""
        elif isinstance(expression.implementation_text, Element):
            # XML serialization (will recreate namespaces)
            default_namespace = next(
                (ns for ns, prefix in self.app_namespaces.items() if prefix == ""), None
            )
            implementation_text = tostring(
                expression.implementation_text,
                xml_declaration=False,
                default_namespace=default_namespace,
            )
        else:
            # Some raw content (e.g. language="python")
            implementation_text = tag_escape(expression.implementation_text)

        self.output.write(
            f'  <QueryExpressionText isPrivate="{is_private}" language="{expression.language}"'
            f' returnFeatureTypes="{types}">{implementation_text}</QueryExpressionText>\n'
        )
