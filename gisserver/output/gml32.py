"""Output rendering logic.

Note that the Django format_html() / mark_safe() logic is not used here,
as it's quite a performance improvement to just use html.escape().
"""
import itertools
import re
from datetime import date, datetime, time
from functools import reduce
from html import escape
from typing import Optional, cast

from django.contrib.gis import geos
from django.contrib.gis.db.models.functions import AsGML, Transform, Union
from django.db import connections, models
from django.http import HttpResponse
from django.utils.timezone import utc

from gisserver.exceptions import NotFound
from gisserver.features import FeatureType
from gisserver.geometries import CRS
from gisserver.parsers.fes20 import ValueReference
from gisserver.types import XsdComplexType, XsdElement

from .base import (
    OutputRenderer,
    StringBuffer,
    build_db_annotations,
    get_db_geometry_selects,
    get_db_geometry_target,
)

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
            self.render_wfs_member(
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
                        self.render_wfs_member(sub_collection.feature_type, instance)
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

    def render_wfs_member(
        self, feature_type: FeatureType, instance: models.Model, extra_xmlns=""
    ) -> str:
        """Write the contents of the object value.

        This output is typically wrapped in <wfs:member> tags
        unless it's used for a GetPropertyById response.
        """
        self.gml_seq = 0  # need to increment this between render_xml_field cals
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
        gml = self.render_bounds(feature_type, instance)
        if gml is not None:
            output.write(gml)

        # Add all members
        for xsd_element in feature_type.xsd_type.elements:
            output.write(self.render_element(feature_type, xsd_element, instance))

        output.write(f"    </app:{feature_type.name}>\n")
        return output.getvalue()

    def render_bounds(self, feature_type, instance) -> Optional[str]:
        """Render the GML bounds for the complete instance"""
        envelope = feature_type.get_envelope(instance, self.output_crs)
        if envelope is not None:
            lower = " ".join(map(str, envelope.lower_corner))
            upper = " ".join(map(str, envelope.upper_corner))
            return f"""      <gml:boundedBy>
              <gml:Envelope srsDimension="2" srsName="{self.xml_srs_name}">
                <gml:lowerCorner>{lower}</gml:lowerCorner>
                <gml:upperCorner>{upper}</gml:upperCorner>
              </gml:Envelope>
            </gml:boundedBy>\n"""

    def render_element(
        self, feature_type, xsd_element: XsdElement, instance: models.Model
    ):
        """Rendering of a single field."""
        value = xsd_element.get_value(instance)
        if xsd_element.is_gml and value is not None:
            # None check happens here to avoid incrementing for none values
            self.gml_seq += 1
            return self.render_gml_field(
                feature_type,
                xsd_element.name,
                value,
                gml_id=self.get_gml_id(feature_type, instance.pk, seq=self.gml_seq),
            )
        else:
            return self.render_xml_field(feature_type, xsd_element, value)

    def render_xml_field(
        self, feature_type: FeatureType, xsd_element: XsdElement, value, extra_xmlns=""
    ) -> str:
        """Write the value of a single field."""
        name = xsd_element.name
        if value is None:
            return f'      <app:{name} xsi:nil="true"{extra_xmlns} />\n'
        elif xsd_element.type.is_complex_type:
            # Expanded foreign relation / dictionary
            xsd_type = cast(XsdComplexType, xsd_element.type)
            output = StringBuffer()
            output.write(f"      <app:{name}>\n")
            for sub_element in xsd_type.elements:
                output.write(
                    self.render_element(feature_type, sub_element, instance=value)
                )
            output.write(f"      </app:{name}>\n")
            return output.getvalue()
        elif isinstance(value, datetime):
            value = value.astimezone(utc).isoformat()
        elif isinstance(value, (date, time)):
            value = value.isoformat()
        elif isinstance(value, bool):
            value = "true" if value else "false"
        else:
            value = escape(str(value))

        return f"      <app:{name}{extra_xmlns}>{value}</app:{name}>\n"

    def render_gml_field(
        self, feature_type: FeatureType, name: str, value, gml_id, extra_xmlns=""
    ) -> str:
        """Write the value of an GML tag"""
        gml = self.render_gml_value(value, gml_id=gml_id)
        return f"      <app:{name}{extra_xmlns}>{gml}</app:{name}>\n"

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
        dim = 3 if value.hasz else 2
        return (
            f"<gml:Point{base_attrs}>"
            f'<gml:pos srsDimension="{dim}">{coords}</gml:pos>'
            f"</gml:Point>"
        )

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
        coords = " ".join(map(str, itertools.chain.from_iterable(value.tuple)))
        dim = "3" if value.hasz else "2"
        # <gml:coordinates> is still valid in GML3, but deprecated (part of GML2).
        return (
            f"<gml:LinearRing{base_attrs}>"
            f'<gml:posList srsDimension="{dim}">{coords}</gml:posList>'
            "</gml:LinearRing>"
        )

    @register_geos_type(geos.LineString)
    def render_gml_line_string(self, value: geos.LineString, base_attrs=""):
        coords = " ".join(map(str, itertools.chain.from_iterable(value.tuple)))
        dim = "3" if value.hasz else "2"
        return (
            f"<gml:LineString{base_attrs}>"
            f'<gml:posList srsDimension="{dim}">{coords}</gml:posList>'
            "</gml:LineString>"
        )

    def get_gml_id(self, feature_type: FeatureType, object_id, seq) -> str:
        """Generate the gml:id value, which is required for GML 3.2 objects."""
        return f"{feature_type.name}.{object_id}.{seq}"


class DBGML32Renderer(GML32Renderer):
    """Faster GetFeature renderer that uses the database to render GML 3.2"""

    @classmethod
    def decorate_queryset(cls, feature_type, queryset, output_crs, **params):
        """Update the queryset to let the database render the GML output.
        This is far more efficient then GeoDjango's logic, which performs a
        C-API call for every single coordinate of a geometry.
        """
        queryset = super().decorate_queryset(
            feature_type, queryset, output_crs, **params
        )

        geometries = get_db_geometry_selects(feature_type.xsd_type, output_crs)
        return queryset.defer(*geometries.keys()).annotate(
            _as_envelope_gml=cls.get_db_envelope_as_gml(
                feature_type, queryset, output_crs
            ),
            **build_db_annotations(geometries, "_as_gml_{name}", _AsGML),
        )

    @classmethod
    def get_prefetch_queryset(cls, xsd_element: XsdElement, output_crs: CRS):
        """Perform DB annotations for the prefetched relation too."""
        xsd_type: XsdComplexType = cast(XsdComplexType, xsd_element.type)
        model = xsd_type.source

        geometries = get_db_geometry_selects(xsd_type, output_crs)
        if geometries:
            return model.objects.defer(*geometries.keys()).annotate(
                **build_db_annotations(geometries, "_as_gml_{name}", _AsGML),
            )

    @classmethod
    def get_db_envelope_as_gml(cls, feature_type, queryset, output_crs) -> AsGML:
        """Offload the GML rendering of the envelope to the database.

        This also avoids offloads the geometry union calculation to the DB.
        """
        geo_fields_union = cls._get_geometries_union(feature_type, queryset, output_crs)
        return _AsGML(geo_fields_union, envelope=True)

    @classmethod
    def _get_geometries_union(cls, feature_type: FeatureType, queryset, output_crs):
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

        if feature_type.geometry_field.srid != output_crs.srid:
            union = Transform(union, output_crs.srid)

        return union

    def render_element(
        self, feature_type, xsd_element: XsdElement, instance: models.Model
    ):
        if xsd_element.is_gml:
            # Optimized path, pre-rendered GML
            value = getattr(instance, f"_as_gml_{xsd_element.name}")
            if value is None:
                # Avoid incrementing gml_seq
                return f'      <app:{xsd_element.name} xsi:nil="true" />\n'

            self.gml_seq += 1
            return self.render_db_gml_field(
                feature_type,
                xsd_element.name,
                value,
                gml_id=self.get_gml_id(feature_type, instance.pk, seq=self.gml_seq),
            )
        else:
            return super().render_element(feature_type, xsd_element, instance)

    def render_db_gml_field(
        self, feature_type: FeatureType, name: str, value, gml_id, extra_xmlns=""
    ) -> str:
        """Write the value of an GML tag"""
        if value is None:
            return f'      <app:{name} xsi:nil="true"{extra_xmlns} />\n'

        # Write the gml:id inside the first tag
        pos = value.find(">")
        first_tag = value[:pos]
        if "gml:id" in first_tag:
            first_tag = RE_GML_ID.sub(f'gml:id="{escape(gml_id)}"', first_tag, 1)
        else:
            first_tag += f' gml:id="{escape(gml_id)}"'

        gml = first_tag + value[pos:]
        return f"      <app:{name}{extra_xmlns}>{gml}</app:{name}>\n"

    def render_bounds(self, feature_type, instance):
        """Generate the <gml:boundedBy> from DB prerendering."""
        gml = instance._as_envelope_gml
        if gml is not None:
            return f"      <gml:boundedBy>{gml}</gml:boundedBy>\n"


class GML32ValueRenderer(GML32Renderer):
    """Render the GetPropertyValue XML output in GML 3.2 format"""

    content_type = "text/xml; charset=utf-8"
    xml_collection_tag = "ValueCollection"

    def __init__(self, *args, value_reference: ValueReference, **kwargs):
        self.value_reference = value_reference
        super().__init__(*args, **kwargs)

    def render_wfs_member(
        self, feature_type: FeatureType, instance: dict, extra_xmlns=""
    ) -> str:
        """Write the XML for a single object."""
        value = instance["member"]
        if isinstance(value, geos.GEOSGeometry):
            gml_id = self.get_gml_id(feature_type, instance["pk"], seq=1)
            return self.render_gml_field(
                feature_type,
                name=self.value_reference.element_name,
                value=value,
                gml_id=gml_id,
                extra_xmlns=extra_xmlns,
            )
        else:
            # The xsd_element is needed so render_xml_field() can render complex types.
            xsd_element = feature_type.resolve_element(self.value_reference.xpath)
            return self.render_xml_field(
                feature_type, xsd_element, value, extra_xmlns=extra_xmlns
            )


class DBGML32ValueRenderer(DBGML32Renderer, GML32ValueRenderer):
    """Faster GetPropertyValue renderer that uses the database to render GML 3.2"""

    @classmethod
    def decorate_queryset(
        cls, feature_type: FeatureType, queryset, output_crs, **params
    ):
        """Update the queryset to let the database render the GML output."""
        value_reference = params["valueReference"]
        xsd_element = feature_type.resolve_element(value_reference.xpath)
        if xsd_element.is_gml:
            # Add 'gml_member' to point to the pre-rendered GML version.
            return queryset.values(
                "pk",
                gml_member=_AsGML(get_db_geometry_target(xsd_element, output_crs)),
            )
        else:
            return queryset

    def render_wfs_member(
        self, feature_type: FeatureType, instance: dict, extra_xmlns=""
    ) -> str:
        """Write the XML for a single object."""
        if "gml_member" in instance:
            gml_id = self.get_gml_id(feature_type, instance["pk"], seq=1)
            return self.render_db_gml_field(
                feature_type,
                self.value_reference.element_name,
                instance["gml_member"],
                gml_id=gml_id,
            )
        else:
            return super().render_wfs_member(
                feature_type, instance, extra_xmlns=extra_xmlns
            )
