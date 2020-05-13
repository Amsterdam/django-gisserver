"""Output rendering logic."""
from datetime import date, datetime, time

from django.contrib.gis.geos import GEOSGeometry, Point
from django.db import models
from django.http import HttpResponse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.timezone import utc

from gisserver.exceptions import NotFound
from gisserver.features import FeatureType
from gisserver.parsers.fes20 import ValueReference

from .base import OutputRenderer, StringBuffer


def default_if_none(value, default):
    if value is None:
        return default
    else:
        return value


class GML32Renderer(OutputRenderer):
    """Render the GetFeature XML output in GML 3.2 format"""

    content_type = "text/xml; charset=utf-8"
    xml_collection_tag = "FeatureCollection"

    def get_response(self):
        """Render the output as streaming response."""
        from gisserver.parsers.queries import GetFeatureById

        if isinstance(self.source_query, GetFeatureById):
            # WFS spec requires that GetFeatureById output only returns the contents.
            # The streaming response is avoided here, to allow returning a 404.
            return HttpResponse(
                content=self.render_xml_standalone(), content_type=self.content_type,
            )
        else:
            # Use default streaming response, with render_stream()
            return super().get_response()

    def render_xmlns(self):
        """Generate the xmlns block that the documente needs"""
        xsd_typenames = ",".join(
            sub_collection.feature_type.name
            for sub_collection in self.collection.results
        )
        schema_location = [
            f"{self.app_xml_namespace} {self.server_url}?SERVICE=WFS&VERSION=2.0.0&REQUEST=DescribeFeatureType&TYPENAMES={xsd_typenames}",  # noqa: E501
            "http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd",
            "http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd",
        ]

        return mark_safe(
            """
     xmlns:app="{app_xml_namespace}"
     xmlns:gml="http://www.opengis.net/gml/3.2"
     xmlns:wfs="http://www.opengis.net/wfs/2.0"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="{schema_location}"
""".format(
                app_xml_namespace=escape(self.app_xml_namespace),
                schema_location=escape(" ".join(schema_location)),
            )
        )

    def render_xmlns_standalone(self):
        """Generate the xmlns block that the documente needs"""
        return format_html(
            ' xmlns:app="{app_xml_namespace}" xmlns:gml="http://www.opengis.net/gml/3.2"',
            app_xml_namespace=self.app_xml_namespace,
        )

    def render_xml_standalone(self):
        """Render a standalone item, for GetFeatureById"""
        sub_collection = self.collection.results[0]
        instance = sub_collection.first()
        if instance is None:
            raise NotFound("Feature not found.")

        output = StringBuffer()
        output.write("""<?xml version='1.0' encoding="UTF-8" ?>\n""")
        output.write(
            self.render_xml_member(
                feature_type=sub_collection.feature_type,
                instance=instance,
                extra_xmlns=self.render_xmlns_standalone(),
            )
        )
        return output.getvalue()

    def render_stream(self):
        """Render the XML as streaming content.
        This renders the standard <wfs:FeatureCollection> / <wfs:ValueCollection>
        """
        collection = self.collection
        output = StringBuffer()
        output.write(
            format_html(
                """<?xml version='1.0' encoding="UTF-8" ?>
<wfs:{xml_collection_tag}
     {xmlns}
     timeStamp="{timestamp}" numberMatched="{number_matched}" numberReturned="{number_returned}"{next}{previous}>\n""",  # noqa: E501
                xml_collection_tag=self.xml_collection_tag,
                xmlns=mark_safe(self.render_xmlns().strip()),
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
                            "    <wfs:{xml_collection_tag}"
                            ' timeStamp="{timestamp}"'
                            ' numberMatched="{number_matched}"'
                            ' numberReturned="{number_returned}">\n',
                            xml_collection_tag=self.xml_collection_tag,
                            timestamp=collection.timestamp,
                            number_returned=sub_collection.number_returned,
                            number_matched=sub_collection.number_matched,
                        )
                    )

                for instance in sub_collection:
                    output.write("  <wfs:member>\n")
                    output.write(
                        self.render_xml_member(sub_collection.feature_type, instance)
                    )
                    output.write("  </wfs:member>\n")

                    # Only perform a 'yield' every once in a while,
                    # as it goes back-and-forth for writing it to the client.
                    if output.is_full():
                        yield output.getvalue()
                        output.clear()

                if has_multiple_collections:
                    output.write(
                        f"    </wfs:{self.xml_collection_tag}>\n  </wfs:member>\n"
                    )

        output.write(f"</wfs:{self.xml_collection_tag}>\n")
        yield output.getvalue()

    def render_xml_member(
        self, feature_type: FeatureType, instance: models.Model, extra_xmlns=""
    ) -> str:
        """Write the contents of the object value."""
        gml_seq = 0
        output = StringBuffer()
        output.write(
            format_html(
                '    <app:{name} gml:id="{name}.{pk}"{extra_xmlns}>\n'
                "      <gml:name>{display}</gml:name>\n",
                name=feature_type.name,
                pk=instance.pk,
                display=str(instance),
                extra_xmlns=extra_xmlns,
            ),
        )

        # Add <gml:boundedBy>
        member_bbox = feature_type.get_envelope(instance, self.output_crs)
        if member_bbox is not None:
            output.write(self.render_gml_bounds(member_bbox))

        for field in feature_type.fields:
            try:
                value = getattr(instance, field)
            except AttributeError:
                # E.g. Django foreign keys that point to a non-existing member.
                value = None

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
        return output.getvalue()

    def render_xml_field(
        self, feature_type: FeatureType, field: str, value, extra_xmlns=""
    ) -> str:
        """Write the value of a single field."""
        if value is None:
            return format_html(
                '    <app:{field} xsi:nil="true"{extra_xmlns} />\n',
                field=field,
                extra_xmlns=extra_xmlns,
            )
        elif isinstance(value, datetime):
            value = value.astimezone(utc).isoformat()
        elif isinstance(value, (date, time)):
            value = value.isoformat()
        elif isinstance(value, bool):
            value = "true" if value else "false"

        return format_html(
            "    <app:{field}{extra_xmlns}>{value}</app:{field}>\n",
            field=field,
            value=value,
            extra_xmlns=extra_xmlns,
        )

    def render_gml_field(
        self, feature_type: FeatureType, name, value, gml_id, extra_xmlns=""
    ) -> str:
        """Write the value of an GML tag"""
        return format_html(
            "      <app:{name}{extra_xmlns}>{gml}</app:{name}>\n",
            name=name,
            gml=self.render_gml_value(value, gml_id=gml_id),
            extra_xmlns=extra_xmlns,
        )

    def render_gml_value(self, value: GEOSGeometry, gml_id: str, extra_xmlns="") -> str:
        """Convert a Geometry into GML syntax."""
        self.output_crs.apply_to(value)
        if isinstance(value, Point):
            return format_html(
                (
                    '<gml:Point gml:id="{gml_id}" srsName="{srs_name}"{extra_xmlns}>'
                    "<gml:pos>{coords}</gml:pos>"
                    "</gml:Point>"
                ),
                gml_id=gml_id,
                srs_name=str(self.output_crs),
                coords=" ".join(map(str, value.coords)),
                extra_xmlns=extra_xmlns,
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
    xml_collection_tag = "ValueCollection"

    def __init__(self, *args, value_reference: ValueReference, **kwargs):
        super().__init__(*args, **kwargs)
        self.element_name = value_reference.element_name

    def render_xml_member(
        self, feature_type: FeatureType, instance: dict, extra_xmlns=""
    ) -> str:
        """Write the XML for a single object."""
        gml_seq = 0
        output = StringBuffer()
        value = instance["member"]
        if isinstance(value, GEOSGeometry):
            gml_seq += 1
            output.write(
                self.render_gml_field(
                    feature_type,
                    name=self.element_name,
                    value=value,
                    gml_id=self.get_gml_id(feature_type, instance["pk"], seq=gml_seq),
                    extra_xmlns=extra_xmlns,
                )
            )
        else:
            output.write(
                self.render_xml_field(
                    feature_type, self.element_name, value, extra_xmlns=extra_xmlns
                )
            )

        return output.getvalue()
