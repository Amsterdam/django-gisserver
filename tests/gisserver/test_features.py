import django
import pytest

from gisserver.features import FeatureField, FeatureType
from gisserver.types import GmlElement, XsdElement, XsdTypes
from tests.test_gisserver import models


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
                GmlElement,
                XsdTypes.gmlPointPropertyType,
                '<element name="location" type="gml:PointPropertyType" minOccurs="0" maxOccurs="1" nillable="true" />',
            ),
        ],
    )
    def test_as_xml(self, field_name, cls_type, xsd_type, xml):
        ff = FeatureField(field_name, model_attribute=field_name, model=models.Restaurant)
        assert ff.xsd_element.as_xml == xml
        assert ff.xsd_element.type == xsd_type
        assert isinstance(ff.xsd_element, cls_type)


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
        ff = FeatureField(
            field_name, model_attribute=field_name, model=models.ModelWithGeneratedFields
        )
        assert ff.xsd_element.as_xml == xml
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
