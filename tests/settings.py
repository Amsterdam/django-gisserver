from environ import Env

env = Env()

SECRET_KEY = "insecure-tests-only"

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://localhost/gisserver",  # default homebrew user is superuser
        engine="django.contrib.gis.db.backends.postgis",
    )
}

INSTALLED_APPS = [
    "gisserver",
    "tests.test_gisserver",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {"loaders": ["django.template.loaders.app_directories.Loader",],},
    },
]


CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

ROOT_URLCONF = __name__

# urls.py part:
urlpatterns = []
