from django.core.exceptions import PermissionDenied

from gisserver.features import FeatureType, ServiceDescription, field
from gisserver.views import WFSView
from tests.constants import RD_NEW
from tests.test_gisserver.models import Restaurant


class DeniedFeatureType(FeatureType):
    def check_permissions(self, request):
        raise PermissionDenied("No access to this feature.")


class PlacesWFSView(WFSView):
    """An simple view that uses the WFSView against our test model."""

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
            Restaurant.objects.all(),
            fields="__all__",  # includes 'tags' as array field, but no relations.
            keywords=["unittest"],
            other_crs=[RD_NEW],
            metadata_url="/feature/restaurants/",
        ),
        FeatureType(
            Restaurant.objects.all(),
            # note: no fields defined.
            name="mini-restaurant",
            keywords=["unittest", "limited-fields"],
            other_crs=[RD_NEW],
            metadata_url="/feature/restaurants-limit/",
        ),
        DeniedFeatureType(Restaurant.objects.none(), name="denied-feature"),
    ]


class ComplexTypesWFSView(PlacesWFSView):
    """An advanced view that has a custom type definition for a foreign key and M2M relation."""

    feature_types = [
        FeatureType(
            Restaurant.objects.all(),
            fields=[
                "id",
                "name",
                field("city", fields=["id", "name"]),
                "location",
                "rating",
                "is_open",
                "created",
                field("opening_hours", fields=["weekday", "start_time", "end_time"]),
                "tags",  # array field
            ],
            other_crs=[RD_NEW],
        ),
    ]


class FlattenedWFSView(PlacesWFSView):
    """An advanced view that has a custom type definition for a foreign key."""

    feature_types = [
        FeatureType(
            Restaurant.objects.all(),
            fields=[
                "id",
                "name",
                field("city-id", model_attribute="city_id"),
                field("city-name", model_attribute="city.name"),
                "location",
                "rating",
                "is_open",
                "created",
                "tags",  # array field
            ],
        ),
    ]
