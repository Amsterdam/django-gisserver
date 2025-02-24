import django
import pytest

from gisserver.features import FeatureField
from gisserver.types import XsdTypes
from tests.test_gisserver.models import ModelWithGeneratedFields


@pytest.mark.skipif(
    django.get_version() < "5", reason="GeneratedField is only available in Django >= 5"
)
@pytest.mark.parametrize(
    "field_name,type,xml,geo",
    [
        (
            "name_reversed",
            XsdTypes.string,
            '<element name="name_reversed" type="string" minOccurs="0" />',
            False,
        ),
        (
            "geometry_translated",
            XsdTypes.gmlPointPropertyType,
            '<element name="geometry_translated" type="gml:PointPropertyType" minOccurs="0" maxOccurs="1" />',
            True,
        ),
    ],
)
def test_generated_field_is_resolved_correctly(field_name, type, xml, geo):
    generated_field = FeatureField(
        field_name, model_attribute=field_name, model=ModelWithGeneratedFields
    )
    assert generated_field._get_xsd_type() == type
    assert generated_field.xsd_element.as_xml == xml
    assert generated_field.xsd_element.is_geometry == geo
