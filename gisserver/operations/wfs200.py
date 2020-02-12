"""Operations that implement the WFS 2.0 spec.

Useful docs:
* http://portal.opengeospatial.org/files/?artifact_id=39967
* https://www.opengeospatial.org/standards/wfs#downloads
* http://schemas.opengis.net/wfs/2.0/
* https://mapserver.org/development/rfc/ms-rfc-105.html
* https://enonline.supermap.com/iExpress9D/API/WFS/WFS200/WFS_2.0.0_introduction.htm
"""
from __future__ import annotations

import math
import re
from urllib.parse import urlencode

import ujson
from django.contrib.gis.geos import Point
from django.http import HttpResponse

from gisserver.exceptions import InvalidParameterValue, VersionNegotiationFailed
from gisserver.features import FeatureType
from gisserver.types import CRS, BoundingBox

from .base import (
    OutputFormat,
    Parameter,
    WFSFeatureMethod,
    WFSMethod,
    UnsupportedParameter,
)

SAFE_VERSION = re.compile(r"\A[0-9.]+\Z")
RE_SAFE_FILENAME = re.compile(r"\A[A-Za-z0-9]+[A-Za-z0-9.]*")  # no dot at the start.


class GetCapabilities(WFSMethod):
    """"This operation returns map features, and available operations this WFS server supports."""

    output_formats = [OutputFormat("text/xml")]
    xml_template_name = "get_capabilities.xml"

    def get_parameters(self):
        # Not calling super, as this differs slightly (e.g. no output formats)
        return [
            Parameter(
                "service",
                required=True,
                in_capabilities=True,
                allowed_values=list(self.view.accept_operations.keys()),
            ),
            Parameter(
                # Version parameter can still be sent,
                # but not mandatory for GetCapabilities
                "version",
                allowed_values=self.view.accept_versions,
            ),
            Parameter(
                "AcceptVersions",
                in_capabilities=True,
                allowed_values=self.view.accept_versions,
                parser=self._parse_accept_versions,
            ),
            Parameter(
                "AcceptFormats",
                in_capabilities=True,
                allowed_values=self.output_formats,
                parser=self._parse_output_format,
                default=self.output_formats[0],
            ),
        ] + self.parameters

    def _parse_accept_versions(self, accept_versions) -> str:
        """Special parsing for the ACCEPTVERSIONS parameter."""
        if "VERSION" in self.view.KVP:
            # Even GetCapabilities can still receive a VERSION argument to fixate it.
            raise InvalidParameterValue(
                "AcceptVersions", "Can't provide both ACCEPTVERSIONS and VERSION"
            )

        matched_versions = set(accept_versions.split(",")).intersection(
            self.view.accept_versions
        )
        if not matched_versions:
            allowed = ", ".join(self.view.accept_versions)
            raise VersionNegotiationFailed(
                "acceptversions",
                f"'{accept_versions}' does not contain supported versions, "
                f"supported are: {allowed}.",
            )

        # Take the highest version (mapserver returns first matching)
        requested_version = sorted(matched_versions, reverse=True)[0]

        # Make sure the views+exceptions continue to operate in this version
        self.view.set_version(requested_version)

        return requested_version

    def __call__(self, **params):
        """GetCapabilities only supports XML output"""
        context = self.get_context_data(**params)
        return self.render_xml(context, **params)

    def get_context_data(self, **params):
        view = self.view

        # The 'service' is not reaad from 'params' to avoid dependency on get_parameters()
        service = view.KVP["SERVICE"]  # is WFS
        service_operations = view.accept_operations[service]
        feature_output_formats = service_operations["GetFeature"].output_formats

        return {
            "service_description": view.get_service_description(service),
            "accept_operations": {
                name: operation(view) for name, operation in service_operations.items()
            },
            "service_constraints": self.view.service_constraints,
            "filter_capabilities": self.view.filter_capabilities,
            "accept_versions": self.view.accept_versions,
            "feature_types": self.view.get_feature_types(),
            "feature_output_formats": feature_output_formats,
            "default_max_features": self.view.max_page_size,
        }


class DescribeFeatureType(WFSFeatureMethod):
    """This returns an XML Schema for the provided objects.
    Each feature is exposed as an XSD definition with it's fields.
    """

    output_formats = [
        OutputFormat("XMLSCHEMA"),
        # OutputFormat("text/xml", subtype="gml/3.1.1"),
    ]
    xml_template_name = "describe_feature_type.xml"
    xml_content_type = "application/gml+xml; version=3.2"  # mandatory for WFS

    def get_context_data(self, typeNames, **params):
        return {"feature_types": typeNames}


class GetFeature(WFSFeatureMethod):
    """This returns the feature details; the individual records based on a query.
    Various query parameters allow limiting the data.
    """

    parameters = [
        Parameter(
            "resultType",
            in_capabilities=True,
            parser=lambda x: x.upper(),
            allowed_values=["RESULTS", "HITS"],
            default="RESULTS",
        ),
        Parameter("srsName", parser=CRS.from_string),
        Parameter("bbox", parser=BoundingBox.from_string),
        Parameter("startIndex", parser=int, default=0),
        Parameter("count", parser=int),  # was called maxFeatures in WFS 1.x
        # Not implemented:
        UnsupportedParameter("filter"),
        UnsupportedParameter("sortBy"),
        UnsupportedParameter("resourceID"),  # query on ID (called featureID in wfs 1.x)
        UnsupportedParameter("propertyName"),  # which fields to return
        UnsupportedParameter("resolve"),  # subresource settings
        UnsupportedParameter("resolveDepth"),
        UnsupportedParameter("resolveTimeout"),
        UnsupportedParameter("namespaces"),  # define output namespaces
        UnsupportedParameter("aliases"),
        UnsupportedParameter("filter_language"),
    ]
    output_formats = [
        OutputFormat("text/xml", subtype="gml/3.1.1"),
        # OutputFormat("gml"),
        OutputFormat("application/json", subtype="geojson", charset="utf-8"),
        # OutputFormat("text/csv"),
        # OutputFormat("shapezip"),
        # OutputFormat("application/zip"),
    ]
    xml_template_name = "get_feature.xml"

    def get_context_data(self, resultType, **params):
        if resultType == "HITS":
            return self.get_context_data_hits(**params)
        elif resultType == "RESULTS":
            return self.get_context_data_results(**params)
        else:
            raise NotImplementedError()

    def get_context_data_hits(self, srsName, **params):
        """Return the context data for the "HITS" type."""
        querysets = self.get_querysets(**params)
        number_matched = sum([qs.count() for qs in querysets])
        return {
            "output_crs": srsName or params["typeNames"][0].crs,
            "feature_collections": [],
            "number_matched": number_matched,
        }

    def get_context_data_results(self, srsName, **params):
        """Return the context data for the "RESULTS" type."""
        querysets = self.get_querysets(**params)

        # Parse pagination settings
        max_page_size = self.view.max_page_size
        start = max(0, params["startIndex"])
        page_size = min(max_page_size, params["count"] or max_page_size)
        stop = start + page_size

        # The querysets are not executed until the very end.
        feature_collections = [
            (qs.feature, qs[start:stop].iterator(), qs.count()) for qs in querysets
        ]
        number_matched = sum(item[2] for item in feature_collections)

        previous = next = None
        if start > 0:
            previous = self._replace_url_params(STARTINDEX=max(0, start - page_size))
        if stop < number_matched:  # TODO: fix for returning multiple typeNames
            next = self._replace_url_params(STARTINDEX=start + page_size)

        return {
            "output_crs": srsName or params["typeNames"][0].crs,
            "feature_collections": feature_collections,
            "number_matched": number_matched,
            "next": next,
            "previous": previous,
        }

    def get_querysets(self, typeNames, **params):
        """Generate querysets for all requested data."""
        return [
            self.filter_queryset(feature, feature.model.objects.all(), **params)
            for feature in typeNames
        ]

    def filter_queryset(self, feature: FeatureType, queryset, bbox, **params):
        """Apply the filters to a single feature type."""
        filters = {}

        # Allow filtering within a bounding box
        if bbox:
            filters[f"{feature.geometry_field_name}__within"] = bbox.as_polygon()

        # TODO: other parameters to support:
        # filter=<fes:...>
        # sortBy=attr+A / +D
        # resourceid=app:Type/gml:name (was featureID in wfs 1.x)
        # propertyName=app:Type/app:field1,app:Type/app:field2
        for name in ("filter", "sortBy", "resourceID", "propertyName"):
            if params[name]:
                raise InvalidParameterValue(name, f"{name} is not supported yet")

        if filters:
            queryset = queryset.filter(**filters)

        # Attach extra property to keep meta-dataa in place
        queryset.feature = feature
        return queryset

    def render_xml(self, context, **params):
        """Improve the context for XML output."""
        # It's not possible the stream the queryset results with the XML format,
        # as the first tag needs to describe the number of results.
        feature_collections = [
            (feature, list(qs), matched)
            for feature, qs, matched in context["feature_collections"]
        ]

        # Determine bounding box of all items
        bounding_box = BoundingBox(math.inf, math.inf, -math.inf, -math.inf)
        for feature, qs, matched in feature_collections:
            for instance in qs:
                geomery_value = getattr(instance, feature.geometry_field_name)
                if geomery_value is None:
                    continue

                if isinstance(geomery_value, Point):
                    bounding_box.extend_to(
                        geomery_value.x,
                        geomery_value.y,
                        geomery_value.x,
                        geomery_value.y,
                    )
                else:
                    raise NotImplementedError(
                        f"Rendering {geomery_value} is not implemented"
                    )

        context["feature_collections"] = feature_collections
        context["number_returned"] = sum(len(qs) for _, qs, _ in feature_collections)
        context["bounding_box"] = bounding_box
        context["xsd_typenames"] = self.view.KVP["TYPENAMES"]
        return super().render_xml(context)

    def render_geojson(self, context, **params):
        # TODO: write JSON as stream instead.

        # Flatten the results, they are not grouped in a second FeatureCollection
        features = []
        for feature, qs, number_matched in context["feature_collections"]:
            for instance in qs:
                geo_value = getattr(instance, feature.geometry_field_name)
                features.append(
                    {
                        "type": "Feature",
                        "id": f"{feature.name}.{instance.pk}",  # foreign member (allowed by spec)
                        "geometry_name": str(
                            instance
                        ),  # foreign member (allowed by spec)
                        # bbox: [x, y, x, y]
                        "geometry": (
                            {
                                # using geom_class instead of geom_type for CamelCasing
                                "type": feature.geometry_field.geom_class.__name__,
                                "coordinates": geo_value.coords,
                            }
                            if geo_value is not None
                            else None
                        ),
                        "properties": {
                            name: getattr(instance, name)
                            for name, _ in feature.fields
                            if name not in feature.geometry_field_names
                        },
                    }
                )

        crs = context["output_crs"]
        context = {
            "type": "FeatureCollection",
            "totalFeatures": context["number_matched"],
            "crs": {"type": "name", "properties": {"name": str(crs)}},
            "features": features,
        }

        return HttpResponse(
            ujson.dumps(context), content_type="application/json; charset=utf-8"
        )

    def _replace_url_params(self, **updates) -> str:
        """Replace a query parameter in the URL"""
        new_params = self.view.KVP.copy()
        new_params.update(updates)
        return f"{self.view.server_url}?{urlencode(new_params)}"
