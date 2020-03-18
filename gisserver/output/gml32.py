"""Output rendering logic."""
from datetime import date, datetime, time

from django.contrib.gis.geos import GEOSGeometry, Point
from django.utils.html import format_html
from django.utils.timezone import utc

from gisserver.features import FeatureType

from .base import GetFeatureOutputRenderer, StringBuffer


class GML32Renderer(GetFeatureOutputRenderer):
    """Render the GetFeature XML output in GML 3.2 format"""

    content_type = "text/xml; charset=utf-8"
    needs_number_matched = True

    def render_get_feature(
        self, feature_collections, number_matched, number_returned, next, previous
    ):
        """Render the XML as streaming content"""

        xsd_typenames = self.context["xsd_typenames"]
        schema_location = [
            f"{self.app_xml_namespace} {self.server_url}?SERVICE=WFS&VERSION=2.0.0&REQUEST=DescribeFeatureType&TYPENAMES={xsd_typenames}",  # noqa: E501
            "http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd",
            "http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd",
        ]

        output = StringBuffer()
        output.write(
            format_html(
                """<?xml version='1.0' encoding="UTF-8" ?>
<wfs:FeatureCollection
     xmlns:app="{app_xml_namespace}"
     xmlns:gml="http://www.opengis.net/gml/3.2"
     xmlns:wfs="http://www.opengis.net/wfs/2.0"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="{schema_location}"
     timeStamp="{timestamp}" numberMatched="{number_matched}" numberReturned="{number_returned}"{next}{previous}>""",  # noqa: E501
                app_xml_namespace=self.app_xml_namespace,
                schema_location=" ".join(schema_location),
                timestamp=self.timestamp,
                number_matched="unknown" if number_matched is None else number_matched,
                number_returned=number_returned,
                next=format_html(' next="{}"', next) if next else "",
                previous=format_html(' previous="{}"', previous) if previous else "",
            )
        )
        if number_returned:
            # <wfs:boundedBy>
            #   <gml:Envelope srsName="{{ bounding_box.crs|default:output_crs }}">
            #     <gml:lowerCorner>{{ bounding_box.lower_corner|join:" " }}</gml:lowerCorner>
            #     <gml:upperCorner>{{ bounding_box.upper_corner|join:" " }}</gml:upperCorner>
            #   </gml:Envelope>
            # </wfs:boundedBy>

            for feature, instances, number_matched in feature_collections:
                if len(feature_collections) > 1:
                    output.write(
                        format_html(
                            "  <wfs:member>\n"
                            "    <wfs:FeatureCollection"
                            ' timeStamp="{timestamp}"'
                            ' numberMatched="{number_matched}"'
                            ' numberReturned="{number_returned}">\n',
                            timestamp=self.timestamp,
                            number_matche=number_matched,
                            number_returned=len(instances),
                        )
                    )

                for instance in instances:
                    output.write(self.render_xml_member(feature, instance))

                    # Only perform a 'yield' every once in a while,
                    # as it goes back-and-forth for writing it to the client.
                    if output.is_full():
                        yield output.getvalue()
                        output.clear()

                if len(feature_collections) > 1:
                    output.write("    </wfs:FeatureCollection>\n  </wfs:member>\n")

        output.write("</wfs:FeatureCollection>\n")
        yield output.getvalue()

    def render_xml_member(self, feature: FeatureType, instance) -> str:
        """Write the XML for a single object."""
        gml_seq = 0
        output = StringBuffer()
        output.write("  <wfs:member>\n")
        output.write(
            format_html(
                '    <app:{name} gml:id="{name}.{pk}">\n',
                name=feature.name,
                pk=instance.pk,
            ),
        )

        member_bbox = feature.get_envelope(instance, self.output_crs)
        if member_bbox is not None:
            output.write(self.render_gml_bounds(member_bbox))

        for field, xs_type in feature.fields:
            value = getattr(instance, field)
            if isinstance(value, GEOSGeometry):
                gml_seq += 1
                output.write(
                    self.render_gml_field(
                        feature,
                        field,
                        value,
                        gml_id=self.get_gml_id(feature, instance, seq=gml_seq),
                    )
                )
            else:
                output.write(self.render_xml_field(feature, field, value))

        output.write(format_html("    </app:{name}>\n", name=feature.name))
        output.write("  </wfs:member>\n")
        return output.getvalue()

    def render_xml_field(self, feature: FeatureType, field: str, value) -> str:
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

    def render_gml_field(self, feature: FeatureType, name, value, gml_id) -> str:
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

    def get_gml_id(self, feature: FeatureType, instance, seq) -> str:
        """Generate the gml:id value, which is required for GML 3.2 objects."""
        return "{prefix}.{id}.{seq}".format(
            prefix=feature.name, id=instance.pk, seq=seq
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
