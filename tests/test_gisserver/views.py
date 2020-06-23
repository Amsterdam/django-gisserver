from django.core.exceptions import PermissionDenied
from django.db import models

from gisserver.features import FeatureType, ServiceDescription
from gisserver.types import XsdComplexType, XsdElement
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


class ComplexFeatureType(FeatureType):
    def get_field_type(self, field_name: str, model_field: models.Field):
        """Generate a XsdComplexType for an related field."""
        if isinstance(model_field, models.ForeignKey):
            model = model_field.remote_field.model
            return XsdComplexType(
                name=f"{model._meta.object_name}Type",
                elements=[
                    XsdElement(
                        f.name,
                        type=self.get_field_type(f.name, f),
                        min_occurs=0,
                        max_occurs=1,
                        nillable=f.null,
                        source=f,
                    )
                    for f in model._meta.get_fields()
                    if not f.is_relation
                ],
                source=model,
            )
        else:
            return super().get_field_type(field_name, model_field)


class ComplexTypesWFSView(PlacesWFSView):
    """An advanced view that has a custom type definition for a foreign key."""

    feature_types = [
        ComplexFeatureType(
            Restaurant.objects.all(),
            fields=["id", "name", "city", "location", "rating", "created"],
            other_crs=[RD_NEW],
        ),
    ]
