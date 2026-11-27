from django.apps import AppConfig


class GisServerConfig(AppConfig):
    name = "gisserver"

    def ready(self):
        from .conf import validate_capabilities_bounding_box_settings

        validate_capabilities_bounding_box_settings()
