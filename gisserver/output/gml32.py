"""Output rendering logic.

Note that the Django format_html() / mark_safe() logic is not used here,
as it's quite a performance improvement to just use html.escape().

We've tried replacing this code with lxml and that turned out to be much slower.
As some functions will be called 5000x, this code is also designed to avoid making
much extra method calls per field. Some bits are non-DRY inlined for this reason.
"""

from __future__ import annotations

import itertools
import re
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal as D
from io import StringIO
from operator import itemgetter
from typing import cast

from django.contrib.gis import geos
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.http import HttpResponse

from gisserver.crs import CRS84
from gisserver.db import (
    AsGML,
    get_db_geometry_target,
    get_db_rendered_geometry,
    get_geometries_union,
    replace_queryset_geometries,
)
from gisserver.exceptions import NotFound, WFSException
from gisserver.geometries import BoundingBox
from gisserver.parsers.xml import xmlns
from gisserver.projection import FeatureProjection, FeatureRelation
from gisserver.types import GeometryXsdElement, GmlBoundedByElement, XsdElement, XsdNode, XsdTypes

from .base import CollectionOutputRenderer, XmlOutputRenderer
from .results import SimpleFeatureCollection
from .utils import (
    attr_escape,
    tag_escape,
    value_to_text,
    value_to_xml_string,
)

GML_RENDER_FUNCTIONS = {}
RE_SRS_NAME = re.compile(r'srsName="([^"]+)"')


def register_geos_type(geos_type):
    def _inc(func):
        GML_RENDER_FUNCTIONS[geos_type] = func
        return func

    return _inc


class GML32Renderer(CollectionOutputRenderer, XmlOutputRenderer):
    """Render the GetFeature XML output in GML 3.2 format"""

    content_type = "text/xml; charset=utf-8"
    content_disposition = 'inline; filename="{typenames} {page} {date}.xml"'
    xml_collection_tag = "FeatureCollection"
    xml_sub_collection_tag = "FeatureCollection"  # Mapserver does not use SimpleFeatureCollection
    chunk_size = 40_000
    gml_seq = 0

    # Aliases to use for XML namespaces
    xml_namespaces = {
        "http://www.opengis.net/wfs/2.0": "wfs",
        "http://www.opengis.net/gml/3.2": "gml",
        "http://www.w3.org/2001/XMLSchema-instance": "xsi",  # for xsi:nil="true" and xsi:schemaLocation.
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.feature_types = [
            feature_type
            for sub_collection in self.collection.results
            for feature_type in sub_collection.feature_types
        ]

        self.build_namespace_map()

    def build_namespace_map(
        self,
    ):
        """Collect all namespaces which namespaces are used by features."""
        try:
            # Make aliases for the feature type elements.
            self.feature_qnames = {
                feature_type: self.feature_to_qname(feature_type)
                for feature_type in self.feature_types
            }
            self.xml_qnames = self._build_xml_qnames()
        except KeyError as e:
            raise ImproperlyConfigured(f"No XML namespace alias defined in WFSView for {e}") from e

    def _build_xml_qnames(self) -> dict[XsdNode, str]:
        """Collect aliases for all rendered elements.
        This uses a defaultdict so optional attributes (e.g. by GetPropertyValue) can also be resolved.
        The dict lookup also speeds up, no need to call ``node_to_qname()`` for each tag.
        """
        known_tags = {
            xsd_element: self.to_qname(xsd_element)
            for sub_collection in self.collection.results
            for xsd_element in sub_collection.projection.all_elements
        }
        return defaultdict(self.to_qname, known_tags)

    def get_response(self):
        """Render the output as streaming response."""
        if self.collection.results and self.collection.results[0].projection.output_standalone:
            # WFS spec requires that GetFeatureById output only returns the contents.
            # The streaming response is avoided here, to allow returning a 404.
            return self.get_by_id_response()
        else:
            # Use default streaming response, with render_stream()
            return super().get_response()

    def get_by_id_response(self):
        """Render a standalone item, for GetFeatureById"""
        sub_collection = self.collection.results[0]
        sub_collection.source_query.finalize_results(sub_collection)  # Allow 404
        self.start_collection(sub_collection)

        instance = sub_collection.first()
        if instance is None:
            raise NotFound("Feature not found.")

        self.app_namespaces.pop(xmlns.wfs20.value)  # not rendering wfs tags.
        self.output = StringIO()
        self._write = self.output.write
        self.write_by_id_response(
            sub_collection, instance, extra_xmlns=f" {self.render_xmlns_attributes()}"
        )
        content = self.output.getvalue()
        return HttpResponse(content, content_type=self.content_type)

    def write_by_id_response(self, sub_collection: SimpleFeatureCollection, instance, extra_xmlns):
        """Default behavior for standalone response is writing a feature (can be changed by GetPropertyValue)"""
        self._write('<?xml version="1.0" encoding="UTF-8"?>\n')
        self.write_feature(
            projection=sub_collection.projection,
            instance=instance,
            extra_xmlns=extra_xmlns,
        )

    def render_xsi_schema_location(self):
        """Render the value for the xsi:schemaLocation="..." block."""
        # Find which namespaces are exposed
        types_by_namespace = defaultdict(list)
        for feature_type in self.feature_types:
            types_by_namespace[feature_type.xml_namespace].append(feature_type)

        # Schema location are pairs of "{namespace-uri} {schema-url} {namespace-uri2} {schema-url2}"
        # WFS server types refer to the endpoint that generates the XML Schema for the given feature.
        schema_locations = []
        for xml_namespace, feature_types in types_by_namespace.items():
            schema_locations.append(xml_namespace)
            schema_locations.append(self.operation.view.get_xml_schema_url(feature_types))

        schema_locations += [
            "http://www.opengis.net/wfs/2.0 http://schemas.opengis.net/wfs/2.0/wfs.xsd",
            "http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd",
        ]
        return " ".join(schema_locations)

    def render_exception(self, exception: Exception):
        """Render the exception in a format that fits with the output.

        The WSF XSD spec has a hidden gem: an ``<wfs:truncatedResponse>`` element
        can be rendered at the end of a feature collection
        to inform the client an error happened during rendering.
        """
        message = super().render_exception(exception)
        buffer = self.output.getvalue()

        # Wrap into <ows:ExceptionReport> tag.
        if not isinstance(exception, WFSException):
            exception = WFSException(message, code=exception.__class__.__name__, status_code=500)
        exception.debug_hint = False

        # Only at the top-level, an exception report can be rendered, close any remaining tags.
        if len(self.collection.results) > 1:
            sub_closing = f"</wfs:{self.xml_sub_collection_tag}>\n</wfs:member>\n"
            if not buffer.endswith(sub_closing):
                buffer += sub_closing

        return (
            f"{buffer}"
            "  <wfs:truncatedResponse>"
            f"{exception.as_xml()}"
            "  </wfs:truncatedResponse>\n"
            f"</wfs:{self.xml_collection_tag}>\n"
        )

    def render_stream(self):
        """Render the XML as streaming content.
        This renders the standard <wfs:FeatureCollection> / <wfs:ValueCollection>
        """
        collection = self.collection
        self.output = output = StringIO()
        self._write = self.output.write

        # The base class peaks the generator and handles early exceptions.
        # Any database exceptions during calculating the number of results
        # are all handled by the main WFS view.
        number_matched = collection.number_matched
        number_matched = int(number_matched) if number_matched is not None else "unknown"
        number_returned = collection.number_returned

        next = previous = ""
        if collection.next:
            next = f' next="{attr_escape(collection.next)}"'
        if collection.previous:
            previous = f' previous="{attr_escape(collection.previous)}"'

        self._write(
            f"""<?xml version='1.0' encoding="UTF-8" ?>\n"""
            f"<wfs:{self.xml_collection_tag} {self.render_xmlns_attributes()}"
            f' xsi:schemaLocation="{attr_escape(self.render_xsi_schema_location())}"'
            f' timeStamp="{collection.timestamp}"'
            f' numberMatched="{number_matched}"'
            f' numberReturned="{int(number_returned)}"'
            f"{next}{previous}>\n"
        )

        if number_returned:
            has_multiple_collections = len(collection.results) > 1

            for sub_collection in collection.results:
                projection = sub_collection.projection
                if projection.output_crs.force_xy and projection.output_crs.is_north_east_order:
                    self._write(
                        "<!--\n"
                        f" NOTE: you are requesting the legacy projection notation '{tag_escape(projection.output_crs.origin)}'."
                        f" Please use '{tag_escape(projection.output_crs.urn)}' instead.\n\n"
                        " This also means output coordinates are ordered in legacy the 'west, north' axis ordering.\n"
                        "\n-->\n"
                    )

                self.start_collection(sub_collection)
                if has_multiple_collections:
                    self._write(
                        f"<wfs:member>\n"
                        f"<wfs:{self.xml_sub_collection_tag}"
                        f' timeStamp="{collection.timestamp}"'
                        f' numberMatched="{int(sub_collection.number_matched)}"'
                        f' numberReturned="{int(sub_collection.number_returned)}">\n'
                    )

                for instance in self.read_features(sub_collection):
                    self.gml_seq = 0  # need to increment this between write_xml_field calls
                    self._write("<wfs:member>\n")
                    self.write_feature(projection, instance)
                    self._write("</wfs:member>\n")

                    # Only perform a 'yield' every once in a while,
                    # as it goes back-and-forth for writing it to the client.
                    if output.tell() > self.chunk_size:
                        xml_chunk = output.getvalue()
                        output.seek(0)
                        output.truncate(0)
                        yield xml_chunk

                if has_multiple_collections:
                    self._write(f"</wfs:{self.xml_sub_collection_tag}>\n</wfs:member>\n")

        self._write(f"</wfs:{self.xml_collection_tag}>\n")
        yield output.getvalue()

    def start_collection(self, sub_collection: SimpleFeatureCollection):
        """Hook to allow initialization per feature type"""

    def write_feature(
        self, projection: FeatureProjection, instance: models.Model, extra_xmlns=""
    ) -> None:
        """Write the contents of the object value.

        This output is typically wrapped in <wfs:member> tags
        unless it's used for a GetPropertyById response.
        """
        feature_type = projection.feature_type
        feature_xml_qname = self.feature_qnames[feature_type]

        # Write <app:FeatureTypeName> start node
        pk = tag_escape(str(instance.pk))
        self._write(f'<{feature_xml_qname} gml:id="{feature_type.name}.{pk}"{extra_xmlns}>\n')
        # Write all fields, both base class and local elements.
        for xsd_element in projection.xsd_root_elements:
            # Note that writing 5000 features with 30 tags means this code make 150.000 method calls.
            # Hence, branching to different rendering styles is branched here instead of making such
            # call into a generic "write_field()" function and stepping out from there.

            if xsd_element.type.is_geometry:
                # Separate call which can be optimized (no need to overload write_xml_field() for all calls).
                self.write_gml_field(projection, xsd_element, instance)
            else:
                value = xsd_element.get_value(instance)
                if xsd_element.is_many:
                    self.write_many(projection, xsd_element, value)
                else:
                    # e.g. <gml:name>, or all other <app:...> nodes.
                    self.write_xml_field(projection, xsd_element, value)

        self._write(f"</{feature_xml_qname}>\n")

    def write_many(self, projection: FeatureProjection, xsd_element: XsdElement, value) -> None:
        """Write a node that has multiple values (e.g. array or queryset)."""
        # some <app:...> node that has multiple values
        if value is None:
            # No tag for optional element (see PropertyIsNull), otherwise xsi:nil node.
            if xsd_element.min_occurs:
                xml_qname = self.xml_qnames[xsd_element]
                self._write(f'<{xml_qname} xsi:nil="true"/>\n')
        else:
            for item in value:
                self.write_xml_field(projection, xsd_element, value=item)

    def write_xml_field(
        self, projection: FeatureProjection, xsd_element: XsdElement, value, extra_xmlns=""
    ):
        """Write the value of a single field."""
        xml_qname = self.xml_qnames[xsd_element]
        if value is None:
            self._write(f'<{xml_qname} xsi:nil="true"{extra_xmlns}/>\n')
        elif xsd_element.type.is_complex_type:
            # Expanded foreign relation / dictionary
            self.write_xml_complex_type(projection, xsd_element, value, extra_xmlns=extra_xmlns)
        else:
            # As this is likely called 150.000 times during a request, this is optimized.
            # Avoided a separate call to value_to_xml_string() and avoided isinstance() here.
            value_cls = value.__class__
            if value_cls is str:  # most cases
                value = tag_escape(value)
            elif value_cls is datetime:
                value = value.astimezone(timezone.utc).isoformat()
            elif value_cls is bool:
                value = "true" if value else "false"
            elif (
                value_cls is not int
                and value_cls is not float
                and value_cls is not D
                and value_cls is not date
                and value_cls is not time
            ):
                # Non-string or custom field that extended a scalar.
                # Any of the other types have a faster f"{value}" translation that produces the correct text.
                value = value_to_xml_string(value)

            self._write(f"<{xml_qname}{extra_xmlns}>{value}</{xml_qname}>\n")

    def write_xml_complex_type(
        self, projection: FeatureProjection, xsd_element: XsdElement, value, extra_xmlns=""
    ) -> None:
        """Write a single field, that consists of sub elements"""
        xml_qname = self.xml_qnames[xsd_element]
        self._write(f"<{xml_qname}{extra_xmlns}>\n")
        for sub_element in projection.xsd_child_nodes[xsd_element]:
            if sub_element.type.is_geometry:
                # Separate call which can be optimized (no need to overload write_xml_field() for all calls).
                self.write_gml_field(projection, sub_element, value)
            else:
                sub_value = sub_element.get_value(value)
                if sub_element.is_many:
                    self.write_many(projection, sub_element, sub_value)
                else:
                    self.write_xml_field(projection, sub_element, sub_value)
        self._write(f"</{xml_qname}>\n")

    def write_gml_field(
        self,
        projection: FeatureProjection,
        geo_element: GeometryXsdElement,
        instance: models.Model,
        extra_xmlns="",
    ) -> None:
        """Separate method to allow overriding this for db-performance optimizations."""
        if geo_element.type is XsdTypes.gmlBoundingShapeType:
            # Special case for <gml:boundedBy>, which doesn't need xsd:nil values, nor a gml:id.
            # The value is not a GEOSGeometry either, as that is not exposed by django.contrib.gis.
            envelope = cast(GmlBoundedByElement, geo_element).get_value(
                instance, crs=projection.output_crs
            )
            if envelope is not None:
                self._write(self.render_gml_bounds(envelope))
        else:
            # Regular geometry elements.
            xml_qname = self.xml_qnames[geo_element]
            value = geo_element.get_value(instance)
            if value is None:
                # Avoid incrementing gml_seq
                self._write(f'<{xml_qname} xsi:nil="true"{extra_xmlns}/>\n')
            else:
                gml_id = self.get_gml_id(instance._meta.object_name, instance.pk)

                # the following is somewhat faster, but will render GML 2, not GML 3.2:
                # gml = value.ogr.gml
                # pos = gml.find(">")  # Will inject the gml:id="..." tag.
                # gml = f"{gml[:pos]} gml:id="{attr_escape(gml_id)}"{gml[pos:]}"

                gml = self.render_gml_value(projection, gml_id, value)
                self._write(f"<{xml_qname}{extra_xmlns}>{gml}</{xml_qname}>\n")

    def get_gml_id(self, prefix: str, object_id) -> str:
        """Generate the gml:id value, which is required for GML 3.2 objects."""
        self.gml_seq += 1
        return f"{prefix}.{object_id}.{self.gml_seq}"

    def render_gml_bounds(self, envelope: BoundingBox) -> str:
        """Render the gml:boundedBy element that contains an Envelope.
        This uses an internal object type,
        as :mod:`django.contrib.gis.geos` only provides a 4-tuple envelope.
        """
        return f"""<gml:boundedBy><gml:Envelope srsDimension="2" srsName="{attr_escape(str(envelope.crs))}">
            <gml:lowerCorner>{envelope.min_x} {envelope.min_y}</gml:lowerCorner>
            <gml:upperCorner>{envelope.max_x} {envelope.max_y}</gml:upperCorner>
          </gml:Envelope></gml:boundedBy>\n"""

    def render_gml_value(
        self,
        projection: FeatureProjection,
        gml_id,
        value: geos.GEOSGeometry | None,
        extra_xmlns="",
    ) -> str:
        """Normal case: 'value' is raw geometry data.."""
        # In case this is a standalone response, this will be the top-level element, hence includes the xmlns.
        base_attrs = f' gml:id="{attr_escape(gml_id)}" srsName="{attr_escape(str(projection.output_crs))}"{extra_xmlns}'
        projection.output_crs.apply_to(value)
        return self._render_gml_type(value, base_attrs=base_attrs)

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
        buf = StringIO()
        buf.write(f"<gml:Polygon{base_attrs}><gml:exterior>{ext_ring}</gml:exterior>")
        for i in range(value.num_interior_rings):
            buf.write("<gml:interior>")
            buf.write(self.render_gml_linear_ring(value[i + 1]))
            buf.write("</gml:interior>")
        buf.write("</gml:Polygon>")
        return buf.getvalue()

    @register_geos_type(geos.GeometryCollection)
    def render_gml_multi_geometry(self, value: geos.GeometryCollection, base_attrs):
        children = "".join(self._render_gml_type(child) for child in value)
        return f"<gml:MultiGeometry{base_attrs}>{children}</gml:MultiGeometry>"

    @register_geos_type(geos.MultiPolygon)
    def render_gml_multi_polygon(self, value: geos.GeometryCollection, base_attrs):
        children = "".join(self._render_gml_type(child) for child in value)
        return f"<gml:MultiPolygon{base_attrs}>{children}</gml:MultiPolygon>"

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


class DBGMLRenderingMixin:

    def render_gml_value(self, projection, gml_id, value: str, extra_xmlns=""):
        """DB optimized: 'value' is pre-rendered GML XML string."""
        # Write the gml:id inside the first tag
        end_pos = value.find(">")
        gml_tag = value[:end_pos]
        id_pos = gml_tag.find("gml:id=")
        if id_pos == -1:
            # Inject
            gml = f'{gml_tag} gml:id="{attr_escape(gml_id)}"{extra_xmlns}{value[end_pos:]}'
        else:
            # Replace
            end_pos1 = gml_tag.find('"', id_pos + 8)
            gml = (
                f"{gml_tag[:id_pos]}"
                f'gml:id="{attr_escape(gml_id)}'
                f"{value[end_pos1:end_pos]}"  # from " right until >
                f"{extra_xmlns}"  # extra namespaces?
                f"{value[end_pos:]}"  # from > and beyond
            )

        return self._fix_db_crs_name(projection, gml)

    def _fix_db_crs_name(self, projection: FeatureProjection, gml: str) -> str:
        if projection.output_crs.force_xy:
            # When legacy output is used, make sure the srsName matches the input.
            # PostgreSQL will still generate the EPSG:xxxx notation.
            return gml.replace(
                'srsName="EPSG:', 'srsName="http://www.opengis.net/gml/srs/epsg.xml#', 1
            )
        elif projection.output_crs == CRS84:
            # Fix PostgreSQL not knowing it's CRS84 or WGS84 (both srid 4326)
            return gml.replace(
                'srsName="urn:ogc:def:crs:EPSG::4326"', 'srsName="urn:ogc:def:crs:OGC::CRS84"', 1
            )
        else:
            return gml


class DBGML32Renderer(DBGMLRenderingMixin, GML32Renderer):
    """Faster GetFeature renderer that uses the database to render GML 3.2"""

    def decorate_queryset(self, projection: FeatureProjection, queryset: models.QuerySet):
        """Update the queryset to let the database render the GML output.
        This is far more efficient than GeoDjango's logic, which performs a
        C-API call for every single coordinate of a geometry.
        """
        queryset = super().decorate_queryset(projection, queryset)

        # Retrieve gml:boundedBy in pre-rendered format.
        if projection.has_bounded_by:
            queryset = queryset.annotate(
                _as_envelope_gml=self.get_db_envelope_as_gml(projection, queryset),
            )

        # Retrieve geometries as pre-rendered instead.
        # Only take the geometries of the current level.
        # The annotations for relations will be handled by prefetches and get_prefetch_queryset()
        use_modern = not projection.output_crs.force_xy
        return replace_queryset_geometries(
            queryset,
            projection.geometry_elements,
            projection.output_crs,
            AsGML,
            is_latlon=use_modern and projection.output_crs.is_north_east_order,
            long_urn=use_modern,
        )

    def get_prefetch_queryset(
        self,
        projection: FeatureProjection,
        feature_relation: FeatureRelation,
    ) -> models.QuerySet | None:
        """Perform DB annotations for prefetched relations too."""
        queryset = super().get_prefetch_queryset(projection, feature_relation)
        if queryset is None:
            return None

        # Find which fields are GML elements
        use_modern = not projection.output_crs.force_xy
        return replace_queryset_geometries(
            queryset,
            feature_relation.geometry_elements,
            projection.output_crs,
            AsGML,
            is_latlon=use_modern and projection.output_crs.is_north_east_order,
            long_urn=use_modern,
        )

    def get_db_envelope_as_gml(self, projection: FeatureProjection, queryset) -> AsGML:
        """Offload the GML rendering of the envelope to the database.

        This also avoids offloads the geometry union calculation to the DB.
        """
        geo_fields_union = self._get_geometries_union(projection, queryset)
        use_modern = not projection.output_crs.force_xy
        return AsGML(
            geo_fields_union,
            envelope=True,
            is_latlon=use_modern and projection.output_crs.is_north_east_order,
            long_urn=use_modern,
        )

    def _get_geometries_union(self, projection: FeatureProjection, queryset):
        """Combine all geometries of the model in a single SQL function."""
        # Apply transforms where needed, in case some geometries use a different SRID.
        return get_geometries_union(
            [
                get_db_geometry_target(geo_element, output_crs=projection.output_crs)
                for geo_element in projection.all_geometry_elements
                if geo_element.source is not None  # excludes GmlBoundedByElement
            ],
            using=queryset.db,
        )

    def write_gml_field(
        self,
        projection: FeatureProjection,
        geo_element: GeometryXsdElement,
        instance: models.Model,
        extra_xmlns="",
    ) -> None:
        """Write the value of an GML tag.

        This optimized version takes a pre-rendered XML from the database query.
        """
        xml_qname = self.xml_qnames[geo_element]
        if geo_element.type is XsdTypes.gmlBoundingShapeType:
            gml = instance._as_envelope_gml
            if gml is None:
                return

            gml = self._fix_db_crs_name(projection, gml)
        else:
            value = get_db_rendered_geometry(instance, geo_element, AsGML)
            if value is None:
                # Avoid incrementing gml_seq, make nil tag.
                self._write(f'<{xml_qname} xsi:nil="true"{extra_xmlns}/>\n')
                return

            # Get gml tag to write as value.
            gml_id = self.get_gml_id(instance._meta.object_name, instance.pk)
            gml = self.render_gml_value(projection, gml_id, value, extra_xmlns=extra_xmlns)

        self._write(f"<{xml_qname}{extra_xmlns}>{gml}</{xml_qname}>\n")


class GML32ValueRenderer(GML32Renderer):
    """Render the GetPropertyValue XML output in GML 3.2 format.

    Geoserver seems to generate the element tag inside each ``<wfs:member>`` element. We've applied this one.
    The GML standard demonstrates to render only their content inside a ``<wfs:member>`` element
    (either plain text or an ``<gml:...>`` tag). Not sure what is right here.
    """

    content_type = "text/xml; charset=utf-8"
    content_type_plain = "text/plain; charset=utf-8"
    content_disposition = 'inline; filename="{typenames} {page} {date}-value.xml"'
    content_disposition_plain = 'inline; filename="{typenames} {page} {date}-value.txt"'
    xml_collection_tag = "ValueCollection"
    xml_sub_collection_tag = "ValueCollection"
    _escape_value = staticmethod(value_to_xml_string)
    gml_value_getter = itemgetter("member")

    def decorate_queryset(self, projection: FeatureProjection, queryset: models.QuerySet):
        # Don't optimize queryset, it only retrieves one value
        # The data is already limited to a ``queryset.values()`` in ``QueryExpression.get_queryset()``.
        return queryset

    def write_by_id_response(
        self, sub_collection: SimpleFeatureCollection, instance: dict, extra_xmlns
    ):
        """The value rendering only renders the value. not a complete feature"""
        if sub_collection.projection.property_value_node.is_attribute:
            # Output as plain text
            self.content_type = self.content_type_plain  # change for this instance!
            self.content_disposition = self.content_disposition_plain
            self._escape_value = value_to_text  # avoid XML escaping
        else:
            self._write('<?xml version="1.0" encoding="UTF-8"?>\n')

        # Write the single tag, no <wfs:member> around it.
        self.write_feature(sub_collection.projection, instance, extra_xmlns=extra_xmlns)

    def write_feature(self, projection: FeatureProjection, instance: dict, extra_xmlns="") -> None:
        """Write the XML for a single object.
        In this case, it's only a single XML tag.
        """
        xsd_node = projection.property_value_node
        if xsd_node.type.is_geometry:
            self.write_gml_field(
                projection,
                cast(GeometryXsdElement, xsd_node),
                instance,
                extra_xmlns=extra_xmlns,
            )
        elif xsd_node.is_attribute:
            value = instance["member"]
            if value is not None:
                value = xsd_node.format_raw_value(instance["member"])  # for gml:id
                value = self._escape_value(value)
                self._write(value)
        elif xsd_node.is_array:
            if (value := instance["member"]) is not None:
                # <wfs:member> doesn't allow multiple items as children, for new render as separate members.
                xml_qname = self.xml_qnames[xsd_node]
                first = True
                for item in value:
                    if item is not None:
                        if not first:
                            self._write("</wfs:member>\n<wfs:member>")

                        item = self._escape_value(item)
                        self._write(f"<{xml_qname}>{item}</{xml_qname}>\n")
                        first = False
        elif xsd_node.type.is_complex_type:
            raise NotImplementedError("GetPropertyValue with complex types is not implemented")
            # self.write_xml_complex_type(projection, self.xsd_node, instance['member'])
        else:
            self.write_xml_field(
                projection,
                cast(XsdElement, xsd_node),
                value=instance["member"],
                extra_xmlns=extra_xmlns,
            )

    def write_gml_field(
        self,
        projection: FeatureProjection,
        geo_element: GeometryXsdElement,
        instance: dict,
        extra_xmlns="",
    ) -> None:
        """Overwritten to allow dict access instead of model access."""
        if geo_element.type is XsdTypes.gmlBoundingShapeType:
            raise NotImplementedError(
                "rendering <gml:boundedBy> in GetPropertyValue is not implemented."
            )

        value = self.gml_value_getter(instance)  # "member" or "gml_member"
        xml_qname = self.xml_qnames[geo_element]
        if value is None:
            # Avoid incrementing gml_seq
            self._write(f'<{xml_qname} xsi:nil="true"{extra_xmlns}/>\n')
            return

        gml_id = self.get_gml_id(geo_element.source.model._meta.object_name, instance["pk"])
        gml = self.render_gml_value(projection, gml_id, value, extra_xmlns=extra_xmlns)
        self._write(f"<{xml_qname}{extra_xmlns}>{gml}</{xml_qname}>\n")


class DBGML32ValueRenderer(DBGMLRenderingMixin, GML32ValueRenderer):
    """Faster GetPropertyValue renderer that uses the database to render GML 3.2"""

    gml_value_getter = itemgetter("gml_member")

    def decorate_queryset(self, projection: FeatureProjection, queryset):
        """Update the queryset to let the database render the GML output."""
        # As this is a classmethod, self.value_reference is not available yet.
        element = projection.property_value_node
        if element.type.is_geometry:
            # Add 'gml_member' to point to the pre-rendered GML version.
            geo_element = cast(GeometryXsdElement, element)
            use_modern = not projection.output_crs.force_xy
            return queryset.values(
                "pk",
                gml_member=AsGML(
                    get_db_geometry_target(geo_element, projection.output_crs),
                    is_latlon=use_modern and projection.output_crs.is_north_east_order,
                    long_urn=use_modern,
                ),
            )
        else:
            return queryset
