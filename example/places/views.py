from gisserver.crs import CRS
from gisserver.features import FeatureType, ServiceDescription, field
from gisserver.views import WFSView

from . import models

RD_NEW = CRS.from_string("urn:ogc:def:crs:EPSG::28992")


class PlacesWFSView(WFSView):
    """A simple view that uses the WFSView against our test model."""

    xml_namespace = "http://example.org/gisserver"

    service_description = ServiceDescription(
        # Metadata for the GetCapabilities call:
        title="Places",
        abstract="Demoing a WFS server written in Django using PostGIS",
        keywords=["django-gisserver", "places", "example"],
        provider_name="City of Amsterdam",
        provider_site="https://github.com/Amsterdam/django-gisserver",
        contact_person="Team Datadiensten",
    )

    feature_types = [
        # The feature types are exposed in the GetCapabilities call.
        # This also provides the field structure out of which the XMLSchema
        # for the DescribeFeatureType call is generated, and which fields to output.
        #
        # The FeatureType class may be overwritten to override logic,
        # and each field() can be overwritten/replaced to insert more complex XsdElement classes.
        # Ultimately, the generated XsdElement structure dictates how everything works.
        #
        # Note that multiple models can be exposed in this single view,
        # by adding more FeatureType entries.
        FeatureType(
            # First example for a more minimal usage:
            models.Province.objects.all(),
            fields=[
                "id",
                "name",
                "geometry",
            ],
        ),
        FeatureType(
            # Second example for a more extended usage:
            models.Place.objects.all(),
            fields=[
                field("id", abstract="Identifer"),
                field("name", abstract="Name of the place"),
                "location",
                field(
                    # Foreign key relation, but flattened.
                    "category",
                    model_attribute="category.name",
                ),
                "has_free_parking",
                "tags",  # array field
                "created",
                field(
                    # Reverse relation:
                    "opening_hours",
                    fields=[
                        "weekday",
                        "start_time",
                        "end_time",
                    ],
                    abstract="Opening hours, can list multiple items",
                ),
                field(
                    # M2M relation:
                    "owners",
                    fields=[
                        "id",
                        "first_name",
                        "last_name",
                    ],
                ),
            ],
            display_field_name="name",  # for gml:name.
            # Additional metadata for the GetCapabilities call:
            title="Places",
            abstract="All areas of interest on the map.",
            other_crs=[RD_NEW],
        ),
    ]
