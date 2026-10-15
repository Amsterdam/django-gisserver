import django
import pytest
from django.core.exceptions import ImproperlyConfigured

from gisserver.features import FeatureField, FeatureType, RelatedGeometryFeatureField
from gisserver.output import XmlSchemaRenderer
from gisserver.types import GeometryXsdElement, XsdElement, XsdTypes
from tests.test_gisserver import models


class _MockXmlSchemaRenderer(XmlSchemaRenderer):
    def __init__(self):
        self.app_namespaces = {}
        self.type_namespaces = {
            "http://www.w3.org/2001/XMLSchema": "",  # no xs:string, but "string"
        }


def _render_element(xsd_element):
    return _MockXmlSchemaRenderer().render_element(xsd_element)


class TestFeatureField:
    """Prove that the FeatureField code will generate the expected XML type."""

    @pytest.mark.parametrize(
        "field_name,cls_type,xsd_type,xml",
        [
            (
                "name",
                XsdElement,
                XsdTypes.string,
                '<element name="name" type="string" minOccurs="0" />',
            ),
            (
                "location",
                GeometryXsdElement,
                XsdTypes.gmlPointPropertyType,
                '<element name="location" type="gml:PointPropertyType" minOccurs="0" maxOccurs="1" nillable="true" />',
            ),
        ],
    )
    def test_as_xml(self, field_name, cls_type, xsd_type, xml):
        ft = FeatureType(models.Restaurant.objects.none(), xml_namespace=None)
        ff = FeatureField(
            field_name, model_attribute=field_name, model=models.Restaurant, feature_type=ft
        )
        element_xml = _render_element(ff.xsd_element)
        assert element_xml == xml
        assert ff.xsd_element.type == xsd_type
        assert isinstance(ff.xsd_element, cls_type)

    def test_related_geometry_bind(self):
        """
        Test that RelatedGeometryFeatureField binds using the absolute dotted path
        and restores the relative model_attribute afterwards.
        """
        ft = FeatureType(models.RestaurantReview.objects.none(), xml_namespace=None)
        ff = RelatedGeometryFeatureField(
            "location",
            absolute_model_attribute="restaurant.location",
            relative_model_attribute="location",
            model=models.RestaurantReview,
            feature_type=ft,
        )

        assert ff.model is models.RestaurantReview
        assert ff.model_field == models.Restaurant._meta.get_field("location")
        assert ff.absolute_model_attribute == "restaurant.location"
        assert ff.model_attribute == "location"

        # Also test xsd values
        assert ff.xsd_element.model_attribute == "location"
        assert ff.xsd_element.absolute_model_attribute == "restaurant.location"

    def test_related_geometry_bind_error(self):
        """Test if the the relatiev model name is restored when binding fails."""
        ff = RelatedGeometryFeatureField(
            "location",
            absolute_model_attribute="restaurant.wrong",
            relative_model_attribute="location",
        )

        with pytest.raises(ImproperlyConfigured):
            ff.bind(models.RestaurantReview)

        assert ff.model_attribute == "location"

    def test_related_geometry_late_bind(self):
        """Support binding after construction."""
        ft = FeatureType(models.RestaurantReview.objects.none(), xml_namespace=None)
        ff = RelatedGeometryFeatureField(
            "location",
            absolute_model_attribute="restaurant.location",
            relative_model_attribute="location",
        )

        ff.bind(models.RestaurantReview, feature_type=ft)

        assert ff.model_field == models.Restaurant._meta.get_field("location")
        assert ff.model_attribute == "location"


@pytest.mark.skipif(
    django.VERSION < (5, 0), reason="GeneratedField is only available in Django >= 5"
)
class TestGeneratedFields:
    @pytest.mark.parametrize(
        "field_name,type,xml",
        [
            # GeneratedField that outputs a CharField
            (
                "name_reversed",
                XsdTypes.string,
                '<element name="name_reversed" type="string" minOccurs="0" />',
            ),
            # GeneratedField that outputs a PointField
            (
                "geometry_translated",
                XsdTypes.gmlPointPropertyType,
                '<element name="geometry_translated" type="gml:PointPropertyType" minOccurs="0" maxOccurs="1" />',
            ),
        ],
    )
    def test_generated_field_is_resolved_correctly(self, field_name, type, xml):
        ft = FeatureType(models.Restaurant.objects.none(), xml_namespace=None)
        ff = FeatureField(
            field_name,
            model_attribute=field_name,
            model=models.ModelWithGeneratedFields,
            feature_type=ft,
        )
        element_xml = _render_element(ff.xsd_element)
        assert element_xml == xml
        assert ff.xsd_element.type == type

    def test_generated_geometry_field(self):
        """Prove that both geometry and generated field are included as geometry field."""
        ft = FeatureType(
            models.ModelWithGeneratedFields.objects.all(),
            fields=["name", "name_reversed", "geometry", "geometry_translated"],
            geometry_field_name="geometry_translated",
        )

        # The geometry_fields attribute should include both geo fields
        geo_fields = [e.name for e in ft.all_geometry_elements]
        assert geo_fields == ["geometry", "geometry_translated"]

        model_fields = [e.source for e in ft.all_geometry_elements]
        assert model_fields == [
            models.ModelWithGeneratedFields.geometry.field,
            models.ModelWithGeneratedFields.geometry_translated.field,
        ]

        # There should be a main geometry_field, which refers to the GeneratedField
        assert ft.main_geometry_element.name == "geometry_translated"
        assert ft.main_geometry_element.orm_path == "geometry_translated"
        assert ft.main_geometry_element.source_srid == 4326
        assert ft.main_geometry_element.type.is_geometry
