import django
from django.core.exceptions import PermissionDenied

from gisserver.features import FeatureType, ServiceDescription, field
from gisserver.views import WFSView
from tests.test_gisserver import models
from tests.utils import RD_NEW


class DeniedFeatureType(FeatureType):
    def check_permissions(self, request):
        raise PermissionDenied("No access to this feature.")


class PlacesWFSView(WFSView):
    """A simple view that uses the WFSView against our test model."""

    xml_namespace = "http://example.org/gisserver"
    service_description = ServiceDescription(
        # While not tested directly, this is still validated against the XSD
        title="Places",
        abstract="Unittesting",
        keywords=["django-gisserver"],
        provider_name="Django",
        provider_site="https://www.example.com/",
        contact_person="django-gisserver",
    )
    feature_types = [
        FeatureType(
            models.Restaurant.objects.all(),
            fields="__all__",  # includes 'tags' as array field, but no relations.
            keywords=["unittest"],
            other_crs=[RD_NEW],
            metadata_url="/feature/restaurants/",
        ),
        FeatureType(
            models.Restaurant.objects.all(),
            # note: no fields defined.
            name="mini-restaurant",
            keywords=["unittest", "limited-fields"],
            other_crs=[RD_NEW],
            metadata_url="/feature/restaurants-limit/",
        ),
        DeniedFeatureType(models.Restaurant.objects.none(), name="denied-feature"),
    ]


class ComplexTypesWFSView(PlacesWFSView):
    """An advanced view that has a custom type definition for a foreign key and M2M relation."""

    feature_types = [
        FeatureType(
            models.Restaurant.objects.all(),
            fields=[
                "id",
                "name",
                field("city", fields=["id", "name"]),  # fk relation
                "location",
                "rating",
                "is_open",
                "created",
                field("opening_hours", fields=["weekday", "start_time", "end_time"]),  # m2m
                "tags",  # array field
            ],
            other_crs=[RD_NEW],
        ),
    ]


class FlattenedWFSView(PlacesWFSView):
    """An advanced view that has a custom type definition for a foreign key."""

    feature_types = [
        FeatureType(
            models.Restaurant.objects.all(),
            fields=[
                "id",
                "name",
                field("city-id", model_attribute="city_id"),
                field("city-name", model_attribute="city.name"),
                field("city-region", model_attribute="city.region"),
                "location",
                "rating",
                "is_open",
                "created",
                "tags",  # array field
            ],
        ),
    ]


class RelatedGeometryWFSView(PlacesWFSView):
    """A view to experiment with a geometry field on a related object."""

    feature_types = [
        FeatureType(
            models.RestaurantReview.objects.all(),
            name="restaurantReview",
            fields=[
                "id",
                field(
                    "restaurant",
                    fields=[
                        "id",
                        "name",
                        field("city", fields=["id", "name"]),  # fk relation
                        "location",  # geometry in nested structure
                        "rating",
                        "is_open",
                        "created",
                        # Also include FK and M2M relationships for testing
                        field("opening_hours", fields=["weekday", "start_time", "end_time"]),
                        "tags",  # array field
                    ],
                ),
                "review",
            ],
            geometry_field_name="restaurant.location",
        ),
        FeatureType(
            models.RestaurantReview.objects.all(),
            name="restaurantReview-auto",
            fields=[
                field(
                    "restaurant",
                    fields=[
                        "id",
                        "name",
                        "location",
                    ],
                ),
                "review",
            ],
            # No geometry_field_name, auto-detect first geometry field.
        ),
    ]


if django.VERSION >= (5, 0):

    class GeneratedFieldWFSView(PlacesWFSView):
        """A view that has a type with GeneratedFields"""

        feature_types = [
            FeatureType(
                models.ModelWithGeneratedFields.objects.all(),
                fields=[
                    "id",
                    "name",
                    "name_reversed",  # GeneratedField(output_field=CharField)
                    "geometry",
                    "geometry_translated",  # GeneratedField(output_field=PointField)
                ],
                other_crs=[RD_NEW],
                geometry_field_name="geometry_translated",
            ),
        ]
