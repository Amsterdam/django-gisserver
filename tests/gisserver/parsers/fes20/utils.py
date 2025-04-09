from __future__ import annotations

from gisserver.features import FeatureType
from gisserver.geometries import WGS84
from gisserver.parsers.fes20 import Filter
from gisserver.parsers.query import CompiledQuery
from gisserver.types import ORMPath, XsdElement, XsdTypes
from tests.test_gisserver import models


def compile_query(filter: Filter) -> CompiledQuery:
    """Allow to compile the filter, without having a whole feature type defined."""
    compiler = CompiledQuery(
        feature_type=_MockFeatureType(
            queryset=models.Restaurant.objects.none(), name="TestFeature"
        )
    )
    q_object = filter.build_query(compiler)
    if q_object is not None:
        compiler.add_lookups(q_object)
    return compiler


class _MockFeatureType(FeatureType):
    xml_prefix = "app"
    name = ""
    xml_name = ""
    crs = WGS84
    other_crs = []
    model = models.Restaurant

    def resolve_element(self, xpath: str):
        """Allow validate_comparison() and ValueReference.parse_xpath() to work."""
        parts = [word.strip() for word in xpath.split("/")]
        orm_path = ORMPath(orm_path="__".join(parts), orm_filters=None)
        orm_path.child = XsdElement(name=parts[-1], type=XsdTypes.anyType)
        return orm_path
