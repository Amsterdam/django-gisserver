import django
import pytest

from gisserver.features import FeatureField, FeatureType
from gisserver.types import XsdTypes
from tests.test_gisserver.models import ModelWithGeneratedFields


@pytest.mark.skipif(
    django.get_version() < "5", reason="GeneratedField is only available in Django >= 5"
)
class TestGeneratedFields:
    @pytest.mark.parametrize(
        "field_name,type,xml,is_geo",
        [
            # GeneratedField that outputs a CharField
            (
                "name_reversed",
                XsdTypes.string,
                '<element name="name_reversed" type="string" minOccurs="0" />',
                False,
            ),
            # GeneratedField that outputs a PointField
            (
                "geometry_translated",
                XsdTypes.gmlPointPropertyType,
                '<element name="geometry_translated" type="gml:PointPropertyType" minOccurs="0" maxOccurs="1" />',
                True,
            ),
        ],
    )
    def test_generated_field_is_resolved_correctly(self, field_name, type, xml, is_geo):
        generated_field = FeatureField(
            field_name, model_attribute=field_name, model=ModelWithGeneratedFields
        )
        assert generated_field._get_xsd_type() == type
        assert generated_field.xsd_element.as_xml == xml
        assert generated_field.xsd_element.is_geometry == is_geo

    def test_feature_type(self):
        ft = FeatureType(
            ModelWithGeneratedFields.objects.all(),
            fields=["name", "name_reversed", "geometry", "geometry_translated"],
            geometry_field_name="geometry_translated",
        )

        # The geometry_fields attribute should include both geo fields
        assert len(ft.geometry_fields) == 2
        assert ModelWithGeneratedFields.geometry_translated.field in ft.geometry_fields
        assert ModelWithGeneratedFields.geometry.field in ft.geometry_fields

        # Each geometry field should be translated to a geometry_element
        assert len(ft.geometry_elements) == 2

        # There should be a main geometry_field, which refers to the GeneratedField
        assert ft.geometry_field_name == "geometry_translated"
        assert ft.geometry_field.srid == 4326

        # the main_geometry_element accesses some attributes, which should also work
        # with a GeneratedField
        assert ft.main_geometry_element.orm_path == "geometry_translated"
        assert ft.main_geometry_element.source.srid == 4326
        assert ft.main_geometry_element.is_geometry
