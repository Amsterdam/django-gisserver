from django.core.exceptions import PermissionDenied

from gisserver.features import FeatureType, ServiceDescription
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
            fields="__all__",
            keywords=["unittest"],
            other_crs=[RD_NEW],
            metadata_url="/feature/restaurants/",
        ),
        FeatureType(
            Restaurant.objects.all(),
            name="mini-restaurant",
            keywords=["unittest", "limited-fields"],
            other_crs=[RD_NEW],
            metadata_url="/feature/restaurants-limit/",
        ),
        DeniedFeatureType(Restaurant.objects.none(), name="denied-feature"),
    ]
