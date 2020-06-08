"""Output rendering logic.

Note that the Django format_html() / mark_safe() logic is not used here,
as it's quite a performance improvement to just use html.escape().
"""
from functools import reduce

import re

import itertools
from datetime import date, datetime, time
from html import escape

from django.contrib.gis import geos
from django.contrib.gis.db.models.functions import AsGML, Transform, Union
from django.db import connections, models
from django.http import HttpResponse
from django.utils.timezone import utc

from gisserver.exceptions import NotFound
from gisserver.features import FeatureType
from gisserver.parsers.fes20 import ValueReference

from .base import OutputRenderer, StringBuffer
from .. import conf

GML_RENDER_FUNCTIONS = {}
RE_GML_ID = re.compile(r'gml:id="[^"]+"')


def default_if_none(value, default):
    if value is None:
        return default
    else:
        return value


class _AsGML(AsGML):
    name = "AsGML"

    def __init__(self, expression, version=3, precision=14, envelope=False, **extra):
        # Note that Django's AsGml, version=2, precision=8
        # the options is postgres-only.
        super().__init__(expression, version, precision, **extra)
        self.envelope = envelope

    def as_postgresql(self, compiler, connection, **extra_context):
        # Fill options parameter (https://postgis.net/docs/ST_AsGML.html)
        options = 33 if self.envelope else 1  # 32 = bbox, 1 = long CRS urn
        template = f"%(function)s(%(expressions)s, {options})"
        return self.as_sql(compiler, connection, template=template, **extra_context)


class ST_Union(Union):
    name = "Union"
    arity = None

    def as_postgresql(self, compiler, connection, **extra_context):
        # PostgreSQL can handle ST_Union(ARRAY(field names)), other databases don't.
        if len(self.source_expressions) > 2:
            extra_context["template"] = f"%(function)s(ARRAY(%(expressions)s))"
        return self.as_sql(compiler, connection, **extra_context)


def register_geos_type(geos_type):
    def _inc(func):
        GML_RENDER_FUNCTIONS[geos_type] = func
        return func

    return _inc


class GML32Renderer(OutputRenderer):
    """Render the GetFeature XML output in GML 3.2 format"""

    content_type = "text/xml; charset=utf-8"
    xml_collection_tag = "FeatureCollection"

    def get_response(self):
        """Render the output as streaming response."""
        from gisserver.queries import GetFeatureById

        if isinstance(self.source_query, GetFeatureById):
            # WFS spec requires that GetFeatureById output only returns the contents.
            # The streaming response is avoided here, to allow returning a 404.
            return HttpResponse(
                content=self.render_xml_standalone(), content_type=self.content_type,
            )
        else:
            # Use default streaming response, with render_stream()
            return super().get_response()

    def decorate_queryset(self, feature_type, queryset):
        """Update the queryset to let the database render the GML output.
        This is far more efficient then GeoDjango's logic, which performs a
        C-API call for every single coordinate of a geometry.
        """
        if not conf.GISSERVER_USE_DB_RENDERING:
            return queryset

        return queryset.annotate(
            _as_envelope_gml=self.get_db_envelope_as_gml(feature_type, queryset),
            **{
                f"_as_gml_{field.name}": self.get_db_as_gml(field)
                for field in feature_type.geometry_fields
            },
        )

    def get_db_as_gml(self, field) -> AsGML:
        """Offload the GML rendering to the database.

        This gives a better performance, as Django GML rendering is slow.
        Django calls the C-api for every single coordinate of a polygon.
        """
        if field.srid != self.output_crs.srid:
            value = Transform(field.name, self.output_crs.srid)
        else:
            value = field.name
        return _AsGML(value)

    def get_db_envelope_as_gml(self, feature_type, queryset) -> AsGML:
        """Offload the GML rendering of the envelope to the database.

        This also avoids offloads the geometry union calculation to the DB.
        """
        geo_fields_union = self._get_geometries_union(feature_type, queryset)
        return _AsGML(geo_fields_union, envelope=True)

    def _get_geometries_union(self, feature_type: FeatureType, queryset):
        """Combine all geometries of the model in a single SQL function."""
        field_names = feature_type.geometry_field_names
        if len(field_names) == 1:
            union = next(iter(field_names))  # fastest in set data type
        elif len(field_names) == 2:
            union = Union(*field_names)
        elif connections[queryset.db].vendor == "postgresql":
            # postgres can handle multiple field names
            union = ST_Union(field_names)
        else:
            # other databases do Union(Union(1, 2), 3)
            union = reduce(Union, field_names)

        if feature_type.geometry_field.srid != self.output_crs.srid:
            union = Transform(union, self.output_crs.srid)

        return union

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

        return """
     xmlns:app="{app_xml_namespace}"
     xmlns:gml="http://www.opengis.net/gml/3.2"
     xmlns:wfs="http://www.opengis.net/wfs/2.0"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="{schema_location}"
""".format(
            app_xml_namespace=escape(self.app_xml_namespace),
            schema_location=escape(" ".join(schema_location)),
        )

    def render_xmlns_standalone(self):
        """Generate the xmlns block that the documente needs"""
        return (
            f' xmlns:app="{escape(self.app_xml_namespace)}"'
            ' xmlns:gml="http://www.opengis.net/gml/3.2"'
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
        xmlns = self.render_xmlns().strip()
        number_matched = collection.number_matched
        number_matched = (
            int(number_matched) if number_matched is not None else "unknown"
        )
        number_returned = collection.number_returned
        next = previous = ""
        if collection.next:
            next = f' next="{escape(collection.next)}"'
        if collection.previous:
            previous = f' previous="{escape(collection.previous)}"'

        output.write(
            f"""<?xml version='1.0' encoding="UTF-8" ?>\n"""
            f"<wfs:{self.xml_collection_tag}\n"
            f"     {xmlns}\n"
            f'     timeStamp="{collection.timestamp}"'
            f' numberMatched="{number_matched}"'
            f' numberReturned="{int(number_returned)}"{next}{previous}>\n'
        )

        if number_returned:
            has_multiple_collections = len(collection.results) > 1

            for sub_collection in collection.results:
                if has_multiple_collections:
                    output.write(
                        f"  <wfs:member>\n"
                        f"    <wfs:{self.xml_collection_tag}"
                        f' timeStamp="{collection.timestamp}"'
                        f' numberMatched="{int(sub_collection.number_matched)}"'
                        f' numberReturned="{int(sub_collection.number_returned)}">\n'
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
            '    <app:{name} gml:id="{name}.{pk}"{extra_xmlns}>\n'
            "      <gml:name>{display}</gml:name>\n".format(
                name=feature_type.name,
                pk=escape(str(instance.pk)),
                display=escape(str(instance)),
                extra_xmlns=extra_xmlns,
            )
        )

        # Add <gml:boundedBy>
        output.write(self._select_render_gml_bounds(feature_type, instance))

        for field, xsd_type in feature_type.fields_with_type:
            if conf.GISSERVER_USE_DB_RENDERING and xsd_type.prefix == "gml":
                # Optimized path, pre-rendered GML
                value = getattr(instance, f"_as_gml_{field}")
                gml_seq += 1
                output.write(
                    self.render_db_gml_field(
                        feature_type,
                        field,
                        value,
                        gml_id=self.get_gml_id(feature_type, instance.pk, seq=gml_seq),
                    )
                )
            else:
                # Regular path, locally rendered XML/GML
                try:
                    value = getattr(instance, field)
                except AttributeError:
                    # E.g. Django foreign keys that point to a non-existing member.
                    value = None

                if isinstance(value, geos.GEOSGeometry):
                    gml_seq += 1
                    output.write(
                        self.render_gml_field(
                            feature_type,
                            field,
                            value,
                            gml_id=self.get_gml_id(
                                feature_type, instance.pk, seq=gml_seq
                            ),
                        )
                    )
                else:
                    output.write(self.render_xml_field(feature_type, field, value))

        output.write(f"    </app:{feature_type.name}>\n")
        return output.getvalue()

    def _select_render_gml_bounds(self, feature_type, instance):
        """See which function should render the <gml:boundedBy> for a single instance."""
        if conf.GISSERVER_USE_DB_RENDERING:
            envelope_db = instance._as_envelope_gml
            if envelope_db is not None:
                return self.render_db_gml_bounds(envelope_db)
        else:
            envelope = feature_type.get_envelope(instance, self.output_crs)
            if envelope is not None:
                return self.render_gml_bounds(envelope)

    def render_xml_field(
        self, feature_type: FeatureType, field: str, value, extra_xmlns=""
    ) -> str:
        """Write the value of a single field."""
        if value is None:
            return f'      <app:{field} xsi:nil="true"{extra_xmlns} />\n'
        elif isinstance(value, datetime):
            value = value.astimezone(utc).isoformat()
        elif isinstance(value, (date, time)):
            value = value.isoformat()
        elif isinstance(value, bool):
            value = "true" if value else "false"

        return f"      <app:{field}{extra_xmlns}>{escape(str(value))}</app:{field}>\n"

    def render_db_gml_field(
        self, feature_type: FeatureType, field: str, value, gml_id, extra_xmlns=""
    ) -> str:
        """Write the value of an GML tag"""
        if value is None:
            return f'      <app:{field} xsi:nil="true"{extra_xmlns} />\n'

        # Write the gml:id inside the first tag
        pos = value.find(">")
        first_tag = value[:pos]
        if "gml:id" in first_tag:
            first_tag = RE_GML_ID.sub(f'gml:id="{escape(gml_id)}"', first_tag, 1)
        else:
            first_tag += f' gml:id="{escape(gml_id)}"'

        gml = first_tag + value[pos:].replace(' srsDimension="2"', "")
        return f"      <app:{field}{extra_xmlns}>{gml}</app:{field}>\n"

    def render_db_gml_bounds(self, gml) -> str:
        """Generate the <gml:boundedBy> from DB prerendering."""
        gml = gml.replace(' srsDimension="2"', "")
        return f"      <gml:boundedBy>{gml}</gml:boundedBy>\n"

    def render_gml_field(
        self, feature_type: FeatureType, field: str, value, gml_id, extra_xmlns=""
    ) -> str:
        """Write the value of an GML tag"""
        gml = self.render_gml_value(value, gml_id=gml_id)
        return f"      <app:{field}{extra_xmlns}>{gml}</app:{field}>\n"

    def render_gml_value(
        self, value: geos.GEOSGeometry, gml_id: str, extra_xmlns=""
    ) -> str:
        """Convert a Geometry into GML syntax."""
        self.output_crs.apply_to(value)
        base_attrs = (
            f' gml:id="{escape(gml_id)}" srsName="{self.xml_srs_name}"{extra_xmlns}'
        )
        return self._render_gml_type(value, base_attrs)

    def _render_gml_type(self, value: geos.GEOSGeometry, base_attrs=""):
        try:
            # Avoid isinstance checks, do a direct lookup
            method = GML_RENDER_FUNCTIONS[value.__class__]
        except KeyError:
            return f"<!-- No rendering implemented for {value.geom_type} -->"
        else:
            return method(self, value, base_attrs=base_attrs)

    @register_geos_type(geos.Point)
    def render_gml_point(self, value: geos.Point, base_attrs=""):
        coords = " ".join(map(str, value.coords))
        dim = ' srsDimension="3"' if value.hasz else ""
        return f"<gml:Point{base_attrs}><gml:pos{dim}>{coords}</gml:pos></gml:Point>"

    @register_geos_type(geos.Polygon)
    def render_gml_polygon(self, value: geos.Polygon, base_attrs=""):
        # lol: http://erouault.blogspot.com/2014/04/gml-madness.html
        ext_ring = self.render_gml_linear_ring(value.exterior_ring)
        tags = [f"<gml:Polygon{base_attrs}><gml:exterior>{ext_ring}</gml:exterior>"]
        for i in range(value.num_interior_rings):
            tags.append("<gml:interior>")
            tags.append(self.render_gml_linear_ring(value[i + 1]))
            tags.append("</gml:interior>")
        tags.append("</gml:Polygon>")
        return "".join(tags)

    @register_geos_type(geos.MultiPolygon)
    def render_gml_multi_geometry(self, value: geos.GeometryCollection, base_attrs):
        children = "".join(self._render_gml_type(child) for child in value)
        return f"<gml:MultiGeometry{base_attrs}>{children}</gml:MultiGeometry>"

    @register_geos_type(geos.MultiLineString)
    def render_gml_multi_line_string(self, value: geos.MultiPoint, base_attrs):
        children = "</gml:lineStringMember><gml:lineStringMember>".join(
            self.render_gml_line_string(child) for child in value
        )
        return (
            f"<gml:MultiLineString{base_attrs}>"
            f"<gml:lineStringMember>{children}</gml:lineStringMember>"
            f"</gml:MultiLineString>"
        )

    @register_geos_type(geos.MultiPoint)
    def render_gml_multi_point(self, value: geos.MultiPoint, base_attrs):
        children = "</gml:pointMember><gml:pointMember>".join(
            self.render_gml_point(child) for child in value
        )
        return (
            f"<gml:MultiPoint{base_attrs}>"
            f"<gml:pointMember>{children}</gml:pointMember>"
            f"</gml:MultiPoint>"
        )

    @register_geos_type(geos.LinearRing)
    def render_gml_linear_ring(self, value: geos.LinearRing, base_attrs=""):
        dim = ' srsDimension="3"' if value.hasz else ""
        coords = " ".join(map(str, itertools.chain.from_iterable(value.tuple)))
        # <gml:coordinates> is still valid in GML3, but deprecated (part of GML2).
        return (
            f"<gml:LinearRing{base_attrs}>"
            f"<gml:posList{dim}>{coords}</gml:posList>"
            "</gml:LinearRing>"
        )

    @register_geos_type(geos.LineString)
    def render_gml_line_string(self, value: geos.LineString, base_attrs=""):
        dim = ' srsDimension="3"' if value.hasz else ""
        coords = " ".join(map(str, itertools.chain.from_iterable(value.tuple)))
        return (
            f"<gml:LineString{base_attrs}>"
            f"<gml:posList{dim}>{coords}</gml:posList>"
            "</gml:LineString>"
        )

    def get_gml_id(self, feature_type: FeatureType, object_id, seq) -> str:
        """Generate the gml:id value, which is required for GML 3.2 objects."""
        return f"{feature_type.name}.{object_id}.{seq}"

    def render_gml_bounds(self, bbox) -> str:
        """Generate the <gml:boundedBy> for an instance."""
        lower = " ".join(map(str, bbox.lower_corner))
        upper = " ".join(map(str, bbox.upper_corner))
        return f"""      <gml:boundedBy>
        <gml:Envelope srsName="{self.xml_srs_name}">
          <gml:lowerCorner>{lower}</gml:lowerCorner>
          <gml:upperCorner>{upper}</gml:upperCorner>
        </gml:Envelope>
      </gml:boundedBy>\n"""


class GML32ValueRenderer(GML32Renderer):
    """Render the GetPropertyValue XML output in GML 3.2 format"""

    content_type = "text/xml; charset=utf-8"
    xml_collection_tag = "ValueCollection"

    def __init__(self, *args, value_reference: ValueReference, **kwargs):
        self.value_reference = value_reference
        self.element_name = self.value_reference.element_name
        super().__init__(*args, **kwargs)

    def decorate_queryset(self, feature_type: FeatureType, queryset):
        """Update the queryset to let the database render the GML output."""
        if not conf.GISSERVER_USE_DB_RENDERING:
            return queryset

        if self.element_name in feature_type.geometry_field_names:
            # Add 'gml_member' to point to the pre-rendered GML version.
            geo_field = feature_type.get_field(self.element_name)
            return queryset.values("pk", gml_member=self.get_db_as_gml(geo_field))
        else:
            return queryset

    def render_xml_member(
        self, feature_type: FeatureType, instance: dict, extra_xmlns=""
    ) -> str:
        """Write the XML for a single object."""
        gml_seq = 0
        output = StringBuffer()
        if conf.GISSERVER_USE_DB_RENDERING and "gml_member" in instance:
            gml_seq += 1
            gml_id = self.get_gml_id(feature_type, instance["pk"], seq=gml_seq)
            output.write(
                self.render_db_gml_field(
                    feature_type,
                    self.element_name,
                    instance["gml_member"],
                    gml_id=gml_id,
                )
            )
        else:
            value = instance["member"]
            if isinstance(value, geos.GEOSGeometry):
                gml_seq += 1
                gml_id = self.get_gml_id(feature_type, instance["pk"], seq=gml_seq)
                output.write(
                    self.render_gml_field(
                        feature_type,
                        field=self.element_name,
                        value=value,
                        gml_id=gml_id,
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
