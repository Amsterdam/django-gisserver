"""Output rendering logic.

Note that the Django format_html() / mark_safe() logic is not used here,
as it's quite a performance improvement to just use html.escape().

We've tried replacing this code with lxml and that turned out to be much slower..
"""

from __future__ import annotations

import itertools
import re
from datetime import date, datetime, time, timezone
from html import escape
from typing import cast

from django.contrib.gis import geos
from django.db import models
from django.http import HttpResponse

from gisserver.db import (
    AsGML,
    build_db_annotations,
    conditional_transform,
    get_db_annotation,
    get_db_geometry_selects,
    get_db_geometry_target,
    get_geometries_union,
)
from gisserver.exceptions import NotFound
from gisserver.features import FeatureRelation, FeatureType
from gisserver.geometries import CRS
from gisserver.parsers.fes20 import ValueReference
from gisserver.types import XsdComplexType, XsdElement

from .base import OutputRenderer
from .buffer import StringBuffer
from .results import SimpleFeatureCollection

GML_RENDER_FUNCTIONS = {}
RE_GML_ID = re.compile(r'gml:id="[^"]+"')


def default_if_none(value, default):
    if value is None:
        return default
    else:
        return value


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
            return self.get_standalone_response()
        else:
            # Use default streaming response, with render_stream()
            return super().get_response()

    def get_standalone_response(self):
        """Render a standalone item, for GetFeatureById"""
        sub_collection = self.collection.results[0]
        self.start_collection(sub_collection)
        instance = sub_collection.first()
        if instance is None:
            raise NotFound("Feature not found.")

        body = self.render_feature(
            feature_type=sub_collection.feature_type,
            instance=instance,
            extra_xmlns=self.render_xmlns_standalone(),
        ).lstrip(" ")

        if body.startswith("<"):
            return HttpResponse(
                content=f'<?xml version="1.0" encoding="UTF-8"?>\n{body}',
                content_type=self.content_type,
            )
        else:
            # Best guess for GetFeatureById combined with
            # GetPropertyValue&VALUEREFERENCE=@gml:id
            return HttpResponse(body, content_type="text/plain")

    def render_xmlns(self):
        """Generate the xmlns block that the document needs"""
        xsd_typenames = ",".join(
            sub_collection.feature_type.name for sub_collection in self.collection.results
        )
        schema_location = [
            f"{self.app_xml_namespace} {self.server_url}?SERVICE=WFS&VERSION=2.0.0&REQUEST=DescribeFeatureType&TYPENAMES={xsd_typenames}",  # noqa: E501
            "http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd",
            "http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd",
        ]

        return (
            'xmlns:wfs="http://www.opengis.net/wfs/2.0" '
            'xmlns:gml="http://www.opengis.net/gml/3.2" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:app="{app_xml_namespace}" '
            'xsi:schemaLocation="{schema_location}"'
        ).format(
            app_xml_namespace=escape(self.app_xml_namespace),
            schema_location=escape(" ".join(schema_location)),
        )

    def render_xmlns_standalone(self):
        """Generate the xmlns block that the document needs"""
        # xsi is needed for "xsi:nil="true"' attributes.
        return (
            f' xmlns:app="{escape(self.app_xml_namespace)}"'
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            ' xmlns:gml="http://www.opengis.net/gml/3.2"'
        )

    def render_stream(self):
        """Render the XML as streaming content.
        This renders the standard <wfs:FeatureCollection> / <wfs:ValueCollection>
        """
        collection = self.collection
        output = StringBuffer()
        xmlns = self.render_xmlns().strip()
        number_matched = collection.number_matched
        number_matched = int(number_matched) if number_matched is not None else "unknown"
        number_returned = collection.number_returned
        next = previous = ""
        if collection.next:
            next = f' next="{escape(collection.next)}"'
        if collection.previous:
            previous = f' previous="{escape(collection.previous)}"'

        output.write(
            f"""<?xml version='1.0' encoding="UTF-8" ?>\n"""
            f"<wfs:{self.xml_collection_tag} {xmlns}"
            f' timeStamp="{collection.timestamp}"'
            f' numberMatched="{number_matched}"'
            f' numberReturned="{int(number_returned)}"'
            f"{next}{previous}>\n"
        )

        if number_returned:
            has_multiple_collections = len(collection.results) > 1

            for sub_collection in collection.results:
                self.start_collection(sub_collection)
                if has_multiple_collections:
                    output.write(
                        f"<wfs:member>\n"
                        f"<wfs:{self.xml_collection_tag}"
                        f' timeStamp="{collection.timestamp}"'
                        f' numberMatched="{int(sub_collection.number_matched)}"'
                        f' numberReturned="{int(sub_collection.number_returned)}">\n'
                    )

                for instance in sub_collection:
                    output.write(self.render_wfs_member(sub_collection.feature_type, instance))

                    # Only perform a 'yield' every once in a while,
                    # as it goes back-and-forth for writing it to the client.
                    if output.is_full():
                        yield output.flush()

                if has_multiple_collections:
                    output.write(f"</wfs:{self.xml_collection_tag}>\n</wfs:member>\n")

        output.write(f"</wfs:{self.xml_collection_tag}>\n")
        yield output.flush()

    def start_collection(self, sub_collection: SimpleFeatureCollection):
        """Hook to allow initialization per feature type"""

    def render_wfs_member(self, feature_type: FeatureType, instance: models.Model, extra_xmlns=""):
        """Write the full <wfs:member> block."""
        body = self.render_feature(feature_type, instance, extra_xmlns=extra_xmlns)
        return f"<wfs:member>\n{body}</wfs:member>\n"

    def render_feature(
        self, feature_type: FeatureType, instance: models.Model, extra_xmlns=""
    ) -> str:
        """Write the contents of the object value.

        This output is typically wrapped in <wfs:member> tags
        unless it's used for a GetPropertyById response.
        """
        self.gml_seq = 0  # need to increment this between render_xml_field calls

        # Write <app:FeatureTypeName> start node
        pk = escape(str(instance.pk))
        output = StringBuffer()
        output.write(f'<{feature_type.xml_name} gml:id="{feature_type.name}.{pk}"{extra_xmlns}>\n')

        # Add all base class members, in their correct ordering
        # By having these as XsdElement objects instead of hard-coded writes,
        # the query/filter logic also works for these elements.
        if feature_type.xsd_type.base.is_complex_type:
            for xsd_element in feature_type.xsd_type.base.elements:
                if xsd_element.xml_name == "gml:boundedBy":
                    # Special case for <gml:boundedBy>, so it will render with
                    # the output CRS and can be overwritten with DB-rendered GML.
                    gml = self.render_bounds(feature_type, instance)
                    if gml is not None:
                        output.write(gml)
                else:
                    # e.g. <gml:name>, or all other <app:...> nodes.
                    self.render_xml_field(feature_type, xsd_element, instance, output)

        # Add all members
        for xsd_element in feature_type.xsd_type.elements:
            self.render_xml_field(feature_type, xsd_element, instance, output)

        output.write(f"</{feature_type.xml_name}>\n")
        return output.getvalue()

    def render_bounds(self, feature_type, instance) -> str | None:
        """Render the GML bounds for the complete instance"""
        envelope = feature_type.get_envelope(instance, self.output_crs)
        if envelope is not None:
            lower = " ".join(map(str, envelope.lower_corner))
            upper = " ".join(map(str, envelope.upper_corner))
            return f"""<gml:boundedBy><gml:Envelope srsDimension="2" srsName="{self.xml_srs_name}">
                <gml:lowerCorner>{lower}</gml:lowerCorner>
                <gml:upperCorner>{upper}</gml:upperCorner>
              </gml:Envelope></gml:boundedBy>\n"""
        else:
            return None

    def render_xml_field(
        self, feature_type, xsd_element: XsdElement, instance: models.Model, output
    ):
        """Rendering of a single field."""
        value = xsd_element.get_value(instance)
        if xsd_element.is_many:
            # some <app:...> node that has multiple values
            if value is None:
                # No tag for optional element (see PropertyIsNull), otherwise xsi:nil node.
                if xsd_element.min_occurs:
                    # <app:field xsi:nil="true"/>
                    output.write(f'<{xsd_element.xml_name} xsi:nil="true"/>\n')
            else:
                # Render the tag multiple times
                if xsd_element.type.is_complex_type:
                    # If the retrieved QuerySet was not filtered yet, do so now. This can't
                    # be done in get_value() because the FeatureType is not known there.
                    value = feature_type.filter_related_queryset(value)

                for item in value:
                    output.write(self._render_xml_field(feature_type, xsd_element, value=item))
        else:
            # Single element node
            if xsd_element.is_geometry:
                # Detected first, need to have instance.pk data here (and instance['pk'] for value rendering)
                output.write(
                    self.render_gml_field(feature_type, xsd_element, value, object_id=instance.pk)
                )
            else:
                output.write(self._render_xml_field(feature_type, xsd_element, value))

    def _render_xml_field(
        self, feature_type: FeatureType, xsd_element: XsdElement, value, extra_xmlns=""
    ) -> str:
        """Write the value of a single field."""
        xml_name = xsd_element.xml_name
        if value is None:
            return f'<{xml_name} xsi:nil="true"{extra_xmlns}/>\n'
        elif xsd_element.type.is_complex_type:
            # Expanded foreign relation / dictionary
            return self.render_xml_complex_type(feature_type, xsd_element, value)
        elif isinstance(value, datetime):
            value = value.astimezone(timezone.utc).isoformat()
        elif isinstance(value, (date, time)):
            value = value.isoformat()
        elif isinstance(value, bool):
            value = "true" if value else "false"
        else:
            value = escape(str(value))

        return f"<{xml_name}{extra_xmlns}>{value}</{xml_name}>\n"

    def render_xml_complex_type(self, feature_type, xsd_element, value) -> str:
        """Write a single field, that consists of sub elements"""
        xsd_type = cast(XsdComplexType, xsd_element.type)
        output = StringBuffer()
        output.write(f"<{xsd_element.xml_name}>\n")
        for sub_element in xsd_type.elements:
            self.render_xml_field(feature_type, sub_element, instance=value, output=output)
        output.write(f"</{xsd_element.xml_name}>\n")
        return output.getvalue()

    def render_gml_field(
        self,
        feature_type: FeatureType,
        xsd_element: XsdElement,
        value: geos.GEOSGeometry | None,
        object_id,
        extra_xmlns="",
    ) -> str:
        """Write the value of an GML tag"""
        xml_name = xsd_element.xml_name
        if value is None:
            # Avoid incrementing gml_seq
            return f'<{xml_name} xsi:nil="true"/>\n'

        self.output_crs.apply_to(value)
        self.gml_seq += 1
        gml_id = self.get_gml_id(feature_type, object_id, seq=self.gml_seq)

        # the following is somewhat faster, but will render GML 2, not GML 3.2:
        # gml = value.ogr.gml
        # pos = gml.find(">")  # Will inject the gml:id="..." tag.
        # return f"<{xml_name}{extra_xmlns}>{gml[:pos]} gml:id="{escape(gml_id)}"{gml[pos:]}</{xml_name}>\n"

        base_attrs = f' gml:id="{escape(gml_id)}" srsName="{self.xml_srs_name}"'
        gml = self._render_gml_type(value, base_attrs)
        return f"<{xml_name}{extra_xmlns}>{gml}</{xml_name}>\n"

    def _render_gml_type(self, value: geos.GEOSGeometry, base_attrs=""):
        """Render an GML value (this is also called from MultiPolygon)."""
        try:
            # Avoid isinstance checks, do a direct lookup
            method = GML_RENDER_FUNCTIONS[value.__class__]
        except KeyError:
            return f"<!-- No rendering implemented for {value.geom_type} -->"
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
        buf = StringBuffer()
        buf.write(f"<gml:Polygon{base_attrs}><gml:exterior>{ext_ring}</gml:exterior>")
        for i in range(value.num_interior_rings):
            buf.write("<gml:interior>")
            buf.write(self.render_gml_linear_ring(value[i + 1]))
            buf.write("</gml:interior>")
        buf.write("</gml:Polygon>")
        return buf.getvalue()

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
        # NOTE: this is super slow. value.tuple performs a C-API call for every point!
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
        # NOTE: this is super slow. value.tuple performs a C-API call for every point!
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
    def decorate_queryset(
        cls,
        feature_type: FeatureType,
        queryset: models.QuerySet,
        output_crs: CRS,
        **params,
    ):
        """Update the queryset to let the database render the GML output.
        This is far more efficient then GeoDjango's logic, which performs a
        C-API call for every single coordinate of a geometry.
        """
        queryset = super().decorate_queryset(feature_type, queryset, output_crs, **params)

        # Retrieve geometries as pre-rendered instead.
        gml_elements = feature_type.xsd_type.geometry_elements
        geo_selects = get_db_geometry_selects(gml_elements, output_crs)
        if geo_selects:
            queryset = queryset.defer(*geo_selects.keys()).annotate(
                _as_envelope_gml=cls.get_db_envelope_as_gml(feature_type, queryset, output_crs),
                **build_db_annotations(geo_selects, "_as_gml_{name}", AsGML),
            )

        return queryset

    @classmethod
    def get_prefetch_queryset(
        cls,
        feature_type: FeatureType,
        feature_relation: FeatureRelation,
        output_crs: CRS,
    ) -> models.QuerySet | None:
        """Perform DB annotations for prefetched relations too."""
        base = super().get_prefetch_queryset(feature_type, feature_relation, output_crs)
        if base is None:
            return None

        # Find which fields are GML elements
        gml_elements = []
        for e in feature_relation.xsd_elements:
            if e.is_geometry:
                # Prefetching a flattened relation
                gml_elements.append(e)
            elif e.type.is_complex_type:
                # Prefetching a complex type
                xsd_type: XsdComplexType = cast(XsdComplexType, e.type)
                gml_elements.extend(xsd_type.geometry_elements)

        geometries = get_db_geometry_selects(gml_elements, output_crs)
        if geometries:
            # Exclude geometries from the fields, fetch them as pre-rendered annotations instead.
            return base.defer(geometries.keys()).annotate(
                **build_db_annotations(geometries, "_as_gml_{name}", AsGML),
            )
        else:
            return base

    @classmethod
    def get_db_envelope_as_gml(cls, feature_type, queryset, output_crs) -> AsGML:
        """Offload the GML rendering of the envelope to the database.

        This also avoids offloads the geometry union calculation to the DB.
        """
        geo_fields_union = cls._get_geometries_union(feature_type, queryset, output_crs)
        return AsGML(geo_fields_union, envelope=True)

    @classmethod
    def _get_geometries_union(cls, feature_type: FeatureType, queryset, output_crs):
        """Combine all geometries of the model in a single SQL function."""
        # Apply transforms where needed, in case some geometries use a different SRID.
        return get_geometries_union(
            [
                conditional_transform(
                    model_field.name,
                    model_field.srid,
                    output_srid=output_crs.srid,
                )
                for model_field in feature_type.geometry_fields
            ],
            using=queryset.db,
        )

    def render_xml_field(
        self, feature_type, xsd_element: XsdElement, instance: models.Model, output
    ):
        if xsd_element.is_geometry:
            # Optimized path, pre-rendered GML
            value = get_db_annotation(instance, xsd_element.name, "_as_gml_{name}")
            output.write(
                self.render_db_gml_field(
                    feature_type,
                    xsd_element,
                    value,
                    object_id=instance.pk,
                )
            )
        else:
            super().render_xml_field(feature_type, xsd_element, instance, output)

    def render_db_gml_field(
        self,
        feature_type: FeatureType,
        xsd_element: XsdElement,
        value: str | None,
        object_id,
        extra_xmlns="",
    ) -> str:
        """Write the value of an GML tag"""
        xml_name = xsd_element.xml_name
        if value is None:
            # Avoid incrementing gml_seq
            return f'<{xsd_element.xml_name} xsi:nil="true"/>\n'

        self.gml_seq += 1
        gml_id = self.get_gml_id(feature_type, object_id, seq=self.gml_seq)

        # Write the gml:id inside the first tag
        pos = value.find(">")
        first_tag = value[:pos]
        if "gml:id" in first_tag:
            first_tag = RE_GML_ID.sub(f'gml:id="{escape(gml_id)}"', first_tag, 1)
        else:
            first_tag += f' gml:id="{escape(gml_id)}"'

        gml = first_tag + value[pos:]
        return f"<{xml_name}{extra_xmlns}>{gml}</{xml_name}>\n"

    def render_bounds(self, feature_type, instance):
        """Generate the <gml:boundedBy> from DB prerendering."""
        gml = instance._as_envelope_gml
        if gml is not None:
            return f"<gml:boundedBy>{gml}</gml:boundedBy>\n"
        else:
            return None


class GML32ValueRenderer(GML32Renderer):
    """Render the GetPropertyValue XML output in GML 3.2 format"""

    content_type = "text/xml; charset=utf-8"
    xml_collection_tag = "ValueCollection"

    def __init__(self, *args, value_reference: ValueReference, **kwargs):
        self.value_reference = value_reference
        super().__init__(*args, **kwargs)
        self.xsd_node = None

    @classmethod
    def decorate_queryset(
        cls,
        feature_type: FeatureType,
        queryset: models.QuerySet,
        output_crs: CRS,
        **params,
    ):
        # Don't optimize queryset, it only retrieves one value
        return queryset

    def start_collection(self, sub_collection: SimpleFeatureCollection):
        # Resolve which XsdNode is being rendered
        match = sub_collection.feature_type.resolve_element(self.value_reference.xpath)
        self.xsd_node = match.child

    def render_wfs_member(self, feature_type: FeatureType, instance: dict, extra_xmlns=""):
        """Overwritten to handle attribute support."""
        if self.xsd_node.is_attribute:
            # When GetPropertyValue selects an attribute, it's value is rendered
            # as plain-text (without spaces!) inside a <wfs:member> element.
            # The format_value() is needed for @gml:id
            body = self.xsd_node.format_value(instance["member"])
            return f"<wfs:member>{body}</wfs:member>\n"
        else:
            # The call to GetPropertyValue selected an element.
            # Render this single element tag inside the <wfs:member> parent.
            body = self.render_feature(feature_type, instance)
            return f"<wfs:member>\n{body}</wfs:member>\n"

    def render_feature(self, feature_type: FeatureType, instance: dict, extra_xmlns="") -> str:
        """Write the XML for a single object.
        In this case, it's only a single XML tag.
        """
        value = instance["member"]
        if self.xsd_node.is_geometry:
            self.gml_seq = 0
            return self.render_gml_field(
                feature_type,
                self.xsd_node,
                value=value,
                object_id=instance["pk"],
                extra_xmlns=extra_xmlns,
            )
        else:
            # The xsd_element is needed so render_xml_field() can render complex types.
            value = self.xsd_node.format_value(value)  # needed for @gml:id
            if self.xsd_node.is_attribute:
                # For GetFeatureById, allow returning raw values
                return str(value)
            else:
                return self._render_xml_field(
                    feature_type,
                    cast(XsdElement, self.xsd_node),
                    value,
                    extra_xmlns=extra_xmlns,
                )


class DBGML32ValueRenderer(DBGML32Renderer, GML32ValueRenderer):
    """Faster GetPropertyValue renderer that uses the database to render GML 3.2"""

    @classmethod
    def decorate_queryset(cls, feature_type: FeatureType, queryset, output_crs, **params):
        """Update the queryset to let the database render the GML output."""
        value_reference = params["valueReference"]
        match = feature_type.resolve_element(value_reference.xpath)
        if match.child.is_geometry:
            # Add 'gml_member' to point to the pre-rendered GML version.
            return queryset.values(
                "pk", gml_member=AsGML(get_db_geometry_target(match, output_crs))
            )
        else:
            return queryset

    def render_wfs_member(self, feature_type: FeatureType, instance: dict, extra_xmlns="") -> str:
        """Write the XML for a single object."""
        if "gml_member" in instance:
            self.gml_seq = 0
            body = self.render_db_gml_field(
                feature_type,
                self.xsd_node,
                instance["gml_member"],
                object_id=instance["pk"],
            )
            return f"<wfs:member>\n{body}</wfs:member>\n"
        else:
            return super().render_wfs_member(feature_type, instance, extra_xmlns=extra_xmlns)
