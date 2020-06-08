from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver

# Whether to use the database for rendering GML / GeoJSON fragments.
# This gives a better performance overall, but output may vary between database vendors.
GISSERVER_USE_DB_RENDERING = getattr(settings, "GISSERVER_USE_DB_RENDERING", True)


@receiver(setting_changed)
def _on_settings_change(setting, value, enter, **kwargs):
    if not setting.startswith("GISSERVER_"):
        return

    globals()[setting] = value
