"""All supported output formats"""
from gisserver import conf

from .base import OutputRenderer
from .geojson import DBGeoJsonRenderer, GeoJsonRenderer
from .gml32 import (
    DBGML32Renderer,
    DBGML32ValueRenderer,
    GML32Renderer,
    GML32ValueRenderer,
)
from .results import FeatureCollection, SimpleFeatureCollection

__all__ = [
    "OutputRenderer",
    "FeatureCollection",
    "SimpleFeatureCollection",
    "DBGeoJsonRenderer",
    "DBGML32Renderer",
    "DBGML32ValueRenderer",
    "GeoJsonRenderer",
    "GML32Renderer",
    "GML32ValueRenderer",
    "geojson_renderer",
    "gml32_renderer",
    "gml32_value_renderer",
]


def select_renderer(native_renderer_class, db_renderer_class):
    """Dynamically select the preferred renderer.
    This allows changing the settings within the app.
    """

    def _dec(*args, **kwargs):
        if conf.GISSERVER_USE_DB_RENDERING:
            return db_renderer_class(*args, **kwargs)
        else:
            return native_renderer_class(*args, **kwargs)

    return _dec


gml32_renderer = select_renderer(GML32Renderer, DBGML32Renderer)
gml32_value_renderer = select_renderer(GML32ValueRenderer, DBGML32ValueRenderer)
geojson_renderer = select_renderer(GeoJsonRenderer, DBGeoJsonRenderer)
