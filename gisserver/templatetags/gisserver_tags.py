from urllib.parse import urljoin

from django.contrib.gis.geos import GEOSGeometry, Point
from django.template import Library
from django.utils.html import format_html

from gisserver.features import FeatureType
from gisserver.types import CRS

register = Library()


@register.filter(name="urljoin")
def urljoin_(fragment, server_url):
    return urljoin(server_url, fragment)


@register.filter
def with_feature_fields(instance, feature: FeatureType):
    return [
        (field, xs_type, getattr(instance, field)) for field, xs_type in feature.fields
    ]


@register.simple_tag
def gml_bounds(feature: FeatureType, instance, output_crs: CRS):
    """Generate the <gml:boundedBy>> for an instance."""
    bbox = feature.get_envelope(instance, output_crs)
    if bbox is None:
        return ""

    return format_html(
        """<gml:boundedBy>
        <gml:Envelope srsName="{srs_name}">
            <gml:lowerCorner>{lower}</gml:lowerCorner>
            <gml:upperCorner>{upper}</gml:upperCorner>
        </gml:Envelope>
    </gml:boundedBy>""",
        srs_name=str(output_crs),
        instance_id=instance.pk,
        lower=" ".join(map(str, bbox.lower_corner)),
        upper=" ".join(map(str, bbox.upper_corner)),
    )


@register.simple_tag(takes_context=True)
def gml_value(context, prefix: str, id, value: GEOSGeometry, output_crs: CRS):
    """Generate the GML for a geometry value."""
    forloop = context["forloop"]
    gml_field_index = forloop.get("gml_field_index", 0) + 1
    forloop["gml_field_index"] = gml_field_index

    if isinstance(value, Point):
        value.transform(output_crs.srid)
        return format_html(
            """<gml:Point gml:id="{prefix}.{id}.{seq}" srsName="{srs_name}">
            <gml:pos>{coords}</gml:pos>
          </gml:Point>""",
            prefix=prefix,
            id=id,
            seq=gml_field_index,
            srs_name=str(output_crs),
            coords=" ".join(map(str, value.coords)),
        )
    else:
        raise NotImplementedError(f"Rendering {value} is not implemented")
