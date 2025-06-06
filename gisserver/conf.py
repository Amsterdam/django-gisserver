import math

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver

_originals = {}

# -- feature flags

# Configure whether the <ows:WGS84BoundingBox> should be included in GetCapabilities.
# This is an expensive operation to calculate, hence it reduces the overall performance.
GISSERVER_CAPABILITIES_BOUNDING_BOX = getattr(
    settings, "GISSERVER_CAPABILITIES_BOUNDING_BOX", True
)

# Whether to use the database for rendering GML / GeoJSON fragments.
# This gives a better performance overall, but output may vary between database vendors.
GISSERVER_USE_DB_RENDERING = getattr(settings, "GISSERVER_USE_DB_RENDERING", True)

# The precision to use for DB rendering. (PostGIS stores reliably up till 15 decimals)
GISSERVER_DB_PRECISION = getattr(settings, "GISSERVER_DB_PRECISION", 15)

# Whether to strictly check whether the provided CRS is accepted.
# Otherwise, all database-supported SRID's are allowed.
GISSERVER_SUPPORTED_CRS_ONLY = getattr(settings, "GISSERVER_SUPPORTED_CRS_ONLY", True)

# Whether the total results need to be counted.
# By disabling this, clients just need to fetch more pages
# 0 = No counting, 1 = all pages, 2 = only for the first page.
GISSERVER_COUNT_NUMBER_MATCHED = getattr(settings, "GISSERVER_COUNT_NUMBER_MATCHED", 1)

# -- output rendering

# Following https://docs.geoserver.org/stable/en/user/services/wfs/axis_order.html here:
# Whether the older EPSG:4326 notation (instead of the OGC recommended styles)
# should render in legacy longitude/latitude (x/y) ordering.
# This increases interoperability with legacy web clients,
# as others use urn:ogc:def:crs:EPSG::4326 or http://www.opengis.net/def/crs/epsg/0/4326.
GISSERVER_FORCE_XY_EPSG_4326 = getattr(settings, "GISSERVER_FORCE_XY_EPSG_4326", True)

# Whether the legacy CRS notation http://www.opengis.net/gml/srs/epsg.xml# should render in X/Y
GISSERVER_FORCE_XY_OLD_CRS = getattr(settings, "GISSERVER_FORCE_XY_OLD_CRS", True)

# Extra output formats for GetFeature (see documentation for details)
GISSERVER_EXTRA_OUTPUT_FORMATS = getattr(settings, "GISSERVER_EXTRA_OUTPUT_FORMATS", {})
GISSERVER_GET_FEATURE_OUTPUT_FORMATS = getattr(
    settings, "GISSERVER_GET_FEATURE_OUTPUT_FORMATS", {}
)

# -- max page size

# Allow tuning the page size without having to override code.
# This corresponds with the "DefaultMaxFeatures" setting.
GISSERVER_DEFAULT_MAX_PAGE_SIZE = getattr(settings, "GISSERVER_DEFAULT_MAX_PAGE_SIZE", 5000)

# CSV exports have a higher default page size, as these results can be streamed.
GISSERVER_GEOJSON_MAX_PAGE_SIZE = getattr(settings, "GISSERVER_GEOJSON_MAX_PAGE_SIZE", math.inf)
GISSERVER_CSV_MAX_PAGE_SIZE = getattr(settings, "GISSERVER_CSV_MAX_PAGE_SIZE", math.inf)

# -- debugging

# Whether to follow the WFS standards strictly (breaks CITE conformance testing)
GISSERVER_WFS_STRICT_STANDARD = getattr(settings, "GISSERVER_WFS_STRICT_STANDARD", False)

# Whether to wrap filter errors in a nice response, or raise an exception
GISSERVER_WRAP_FILTER_DB_ERRORS = getattr(settings, "GISSERVER_WRAP_FILTER_DB_ERRORS", True)


@receiver(setting_changed)
def _on_settings_change(setting, value, enter, **kwargs):
    if not setting.startswith("GISSERVER_"):
        return

    conf_module = globals()
    if value is None and not enter:
        # override_settings().disable() returns what the django settings module had.
        # Revert to our defaults here instead.
        value = _originals.get(setting)
    else:
        # Track defaults of this file for reverting to them
        _originals.setdefault(setting, conf_module[setting])

    conf_module[setting] = value
