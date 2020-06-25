import math

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver

# Whether to use the database for rendering GML / GeoJSON fragments.
# This gives a better performance overall, but output may vary between database vendors.
GISSERVER_USE_DB_RENDERING = getattr(settings, "GISSERVER_USE_DB_RENDERING", True)

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


@receiver(setting_changed)
def _on_settings_change(setting, value, enter, **kwargs):
    if not setting.startswith("GISSERVER_"):
        return

    globals()[setting] = value
