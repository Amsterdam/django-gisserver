# Settings file to allow parsing API documentation of Django modules,
# and provide defaults to use in the documentation.
#
# This file is placed in a subdirectory,
# so the docs root won't be detected by find_packages()

# Display sane URLs in the docs:
STATIC_URL = "/static/"

# Required by Django
SECRET_KEY = "foo"
SITE_ID = 1

INSTALLED_APPS = ["gisserver"]

MIDDLEWARE = []

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": (),
        "OPTIONS": {
            "loaders": (
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            )
        },
    }
]
