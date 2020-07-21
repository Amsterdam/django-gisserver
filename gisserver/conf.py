import math

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver

# -- feature flags

# Configure whether the <ows:WGS84BoundingBox> should be included in GetCapabilities.
# This is an expensive operation to calculate, hence it reduces the overall performance.
GISSERVER_CAPABILITIES_BOUNDING_BOX = getattr(
    settings, "GISSERVER_CAPABILITIES_BOUNDING_BOX", True
)

# Whether to use the database for rendering GML / GeoJSON fragments.
# This gives a better performance overall, but output may vary between database vendors.
GISSERVER_USE_DB_RENDERING = getattr(settings, "GISSERVER_USE_DB_RENDERING", True)

# Whether to strictly check whether the provided CRS is accepted.
# Otherwise, all database-supported SRID's are allowed.
GISSERVER_SUPPORTED_CRS_ONLY = getattr(settings, "GISSERVER_SUPPORTED_CRS_ONLY", True)

# -- max page size

# Allow tuning the page size without having to override code.
# This corresponds with the "DefaultMaxFeatures" setting.
GISSERVER_DEFAULT_MAX_PAGE_SIZE = getattr(
    settings, "GISSERVER_DEFAULT_MAX_PAGE_SIZE", 5000
)

# CSV exports have a higher default page size, as these results can be streamed.
GISSERVER_GEOJSON_MAX_PAGE_SIZE = getattr(
    settings, "GISSERVER_GEOJSON_MAX_PAGE_SIZE", math.inf
)
GISSERVER_CSV_MAX_PAGE_SIZE = getattr(settings, "GISSERVER_CSV_MAX_PAGE_SIZE", math.inf)

# -- debugging

# Whether to follow the WFS standards strictly (breaks CITE conformance testing)
GISSERVER_WFS_STRICT_STANDARD = getattr(
    settings, "GISSERVER_WFS_STRICT_STANDARD", False
)

# Whether to wrap filter errors in a nice response, or raise an exception
GISSERVER_WRAP_FILTER_DB_ERRORS = getattr(
    settings, "GISSERVER_WRAP_FILTER_DB_ERRORS", True
)


@receiver(setting_changed)
def _on_settings_change(setting, value, enter, **kwargs):
    if not setting.startswith("GISSERVER_"):
        return

    globals()[setting] = value
