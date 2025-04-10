from __future__ import annotations

from gisserver.features import FeatureType
from gisserver.geometries import WGS84
from gisserver.parsers.fes20 import Filter
from gisserver.parsers.query import CompiledQuery
from gisserver.types import ORMPath, XsdElement, XsdTypes
from tests.test_gisserver import models


def compile_query(filter: Filter, feature_type_names: list[str] | None = None) -> CompiledQuery:
    """Allow to compile the filter, without having a whole feature type defined."""
    if feature_type_names is None:
        feature_type_names = ["TestFeature"]

    compiler = CompiledQuery(feature_types=[_MockFeatureType(n) for n in feature_type_names])
    q_object = filter.build_query(compiler)
    if q_object is not None:
        compiler.add_lookups(q_object)
    return compiler


class _MockFeatureType(FeatureType):
    xml_namespace = "http://example.org/gisserver"
    name = ""
    xml_name = ""
    crs = WGS84
    other_crs = []
    model = models.Restaurant

    def __init__(self, name):
        self.name = name
        self.xml_name = f"{{{self.xml_namespace}}}{name}"

    def resolve_element(self, xpath: str, ns_aliases: dict[str, str]):
        """Allow ValueReference.parse_xpath() to work."""
        parts = [word.strip() for word in xpath.split("/")]
        orm_path = ORMPath(orm_path="__".join(parts), orm_filters=None)
        orm_path.child = XsdElement(
            name=parts[-1], type=XsdTypes.anyType, namespace=self.xml_namespace
        )
        return orm_path
