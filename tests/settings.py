from environ import Env

env = Env()

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://localhost/gisserver",  # default homebrew user is superuser
        engine="django.contrib.gis.db.backends.postgis",
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

GISSERVER_USE_DB_RENDERING = env.bool("GISSERVER_USE_DB_RENDERING", default=True)
GISSERVER_WRAP_FILTER_DB_ERRORS = False  # Raise errors to see what's happening.

INSTALLED_APPS = [
    "gisserver",
    "tests.test_gisserver",
    "django.contrib.postgres",
]

# Test session requirements

SECRET_KEY = "insecure-tests-only"

TIME_ZONE = "Europe/Amsterdam"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {"loaders": ["django.template.loaders.app_directories.Loader"]},
    },
]

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

ROOT_URLCONF = __name__

# urls.py part:
urlpatterns = []
