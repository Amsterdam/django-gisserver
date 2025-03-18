"""Compatability imports"""

import sys

import django
from django.conf import settings
from django.db import models

if (
    "django.contrib.postgres" in settings.INSTALLED_APPS
    or "django.contrib.postgres" in sys.modules
):
    from django.contrib.postgres.fields import ArrayField
else:
    ArrayField = None

GeneratedField = models.GeneratedField if django.VERSION >= (5, 0) else None


__all__ = (
    "ArrayField",
    "GeneratedField",
)
