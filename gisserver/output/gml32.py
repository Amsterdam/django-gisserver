"""Output rendering logic."""
from datetime import date, datetime, time

from django.contrib.gis.geos import GEOSGeometry, Point
from django.db import models
from django.utils.html import format_html
from django.utils.timezone import utc

from gisserver.features import FeatureType
from gisserver.parsers.fes20.expressions import ValueReference

from .base import OutputRenderer, StringBuffer


def default_if_none(value, default):
    if value is None:
        return default
    else:
        return value


class GML32Renderer(OutputRenderer):
    """Render the GetFeature XML output in GML 3.2 format"""

    content_type = "text/xml; charset=utf-8"
    xml_tag = "FeatureCollection"

    def render_stream(self):
        """Render the XML as streaming content"""
        xsd_typenames = self.xsd_typenames
        schema_location = [
            f"{self.app_xml_namespace} {self.server_url}?SERVICE=WFS&VERSION=2.0.0&REQUEST=DescribeFeatureType&TYPENAMES={xsd_typenames}",  # noqa: E501
            "http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd",
            "http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd",
        ]

        collection = self.collection
        output = StringBuffer()
        output.write(
            format_html(
                """<?xml version='1.0' encoding="UTF-8" ?>
<wfs:{xml_tag}
     xmlns:app="{app_xml_namespace}"
     xmlns:gml="http://www.opengis.net/gml/3.2"
     xmlns:wfs="http://www.opengis.net/wfs/2.0"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="{schema_location}"
     timeStamp="{timestamp}" numberMatched="{number_matched}" numberReturned="{number_returned}"{next}{previous}>\n""",  # noqa: E501
                xml_tag=self.xml_tag,
                app_xml_namespace=self.app_xml_namespace,
                schema_location=" ".join(schema_location),
                timestamp=collection.timestamp,
                number_matched=default_if_none(collection.number_matched, "unknown"),
                number_returned=collection.number_returned,
                next=format_html(' next="{}"', collection.next)
                if collection.next
                else "",
                previous=format_html(' previous="{}"', collection.previous)
                if collection.previous
                else "",
            )
        )
        if collection.number_returned:
            # <wfs:boundedBy>
            #   <gml:Envelope srsName="{{ bounding_box.crs|default:output_crs }}">
            #     <gml:lowerCorner>{{ bounding_box.lower_corner|join:" " }}</gml:lowerCorner>
            #     <gml:upperCorner>{{ bounding_box.upper_corner|join:" " }}</gml:upperCorner>
            #   </gml:Envelope>
            # </wfs:boundedBy>
            has_multiple_collections = len(collection.results) > 1

            for sub_collection in collection.results:
                if has_multiple_collections:
                    output.write(
                        format_html(
                            "  <wfs:member>\n"
                            "    <wfs:{xml_tag}"
                            ' timeStamp="{timestamp}"'
                            ' numberMatched="{number_matched}"'
                            ' numberReturned="{number_returned}">\n',
                            xml_tag=self.xml_tag,
                            timestamp=collection.timestamp,
                            number_returned=sub_collection.number_returned,
                            number_matched=sub_collection.number_matched,
                        )
                    )

                for instance in sub_collection:
                    output.write(
                        self.render_xml_member(sub_collection.feature_type, instance)
                    )

                    # Only perform a 'yield' every once in a while,
                    # as it goes back-and-forth for writing it to the client.
                    if output.is_full():
                        yield output.getvalue()
                        output.clear()

                if has_multiple_collections:
                    output.write(f"    </wfs:{self.xml_tag}>\n  </wfs:member>\n")

        output.write(f"</wfs:{self.xml_tag}>\n")
        yield output.getvalue()

    def render_xml_member(
        self, feature_type: FeatureType, instance: models.Model
    ) -> str:
        """Write the XML for a single object."""
        gml_seq = 0
        output = StringBuffer()
        output.write("  <wfs:member>\n")
        output.write(
            format_html(
                '    <app:{name} gml:id="{name}.{pk}">\n'
                "      <gml:name>{display}</gml:name>\n",
                name=feature_type.name,
                pk=instance.pk,
                display=str(instance),
            ),
        )

        # Add <gml:boundedBy>
        member_bbox = feature_type.get_envelope(instance, self.output_crs)
        if member_bbox is not None:
            output.write(self.render_gml_bounds(member_bbox))

        for field in feature_type.fields:
            value = getattr(instance, field)
            if isinstance(value, GEOSGeometry):
                gml_seq += 1
                output.write(
                    self.render_gml_field(
                        feature_type,
                        field,
                        value,
                        gml_id=self.get_gml_id(feature_type, instance.pk, seq=gml_seq),
                    )
                )
            else:
                output.write(self.render_xml_field(feature_type, field, value))

        output.write(format_html("    </app:{name}>\n", name=feature_type.name))
        output.write("  </wfs:member>\n")
        return output.getvalue()

    def render_xml_field(self, feature_type: FeatureType, field: str, value) -> str:
        """Write the value of a single field."""
        if value is None:
            return format_html('    <app:{field} xsi:nil="true" />\n', field=field)
        elif isinstance(value, datetime):
            value = value.astimezone(utc).isoformat()
        elif isinstance(value, (date, time)):
            value = value.isoformat()
        elif isinstance(value, bool):
            value = "true" if value else "false"

        return format_html(
            "    <app:{field}>{value}</app:{field}>\n", field=field, value=value
        )

    def render_gml_field(self, feature_type: FeatureType, name, value, gml_id) -> str:
        """Write the value of an GML tag"""
        return format_html(
            "      <app:{name}>{gml}</app:{name}>\n",
            name=name,
            gml=self.render_gml_value(value, gml_id=gml_id),
        )

    def render_gml_value(self, value: GEOSGeometry, gml_id: str) -> str:
        """Convert a Geometry into GML syntax."""
        self.output_crs.apply_to(value)
        if isinstance(value, Point):
            return format_html(
                (
                    '<gml:Point gml:id="{gml_id}" srsName="{srs_name}">'
                    "<gml:pos>{coords}</gml:pos>"
                    "</gml:Point>"
                ),
                gml_id=gml_id,
                srs_name=str(self.output_crs),
                coords=" ".join(map(str, value.coords)),
            )

    def get_gml_id(self, feature_type: FeatureType, object_id, seq) -> str:
        """Generate the gml:id value, which is required for GML 3.2 objects."""
        return "{prefix}.{id}.{seq}".format(
            prefix=feature_type.name, id=object_id, seq=seq
        )

    def render_gml_bounds(self, bbox) -> str:
        """Generate the <gml:boundedBy>> for an instance."""
        return format_html(
            """    <gml:boundedBy>
        <gml:Envelope srsName="{srs_name}">
            <gml:lowerCorner>{lower}</gml:lowerCorner>
            <gml:upperCorner>{upper}</gml:upperCorner>
        </gml:Envelope>
    </gml:boundedBy>\n""",
            srs_name=str(self.output_crs),
            lower=" ".join(map(str, bbox.lower_corner)),
            upper=" ".join(map(str, bbox.upper_corner)),
        )


class GML32ValueRenderer(GML32Renderer):
    """Render the GetPropertyValue XML output in GML 3.2 format"""

    content_type = "text/xml; charset=utf-8"
    xml_tag = "ValueCollection"

    def __init__(self, *args, value_reference: ValueReference, **kwargs):
        super().__init__(*args, **kwargs)
        self.element_name = value_reference.element_name

    def render_xml_member(self, feature_type: FeatureType, instance: dict) -> str:
        """Write the XML for a single object."""
        gml_seq = 0
        output = StringBuffer()
        output.write("  <wfs:member>\n")

        value = instance["member"]
        if isinstance(value, GEOSGeometry):
            gml_seq += 1
            output.write(
                self.render_gml_field(
                    feature_type,
                    name=self.element_name,
                    value=value,
                    gml_id=self.get_gml_id(feature_type, instance["pk"], seq=gml_seq),
                )
            )
        else:
            output.write(self.render_xml_field(feature_type, self.element_name, value))

        output.write("  </wfs:member>\n")
        return output.getvalue()
