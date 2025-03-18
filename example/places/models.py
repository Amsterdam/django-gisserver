import calendar
from datetime import time

from django.contrib.auth.models import User
from django.contrib.gis.db.models import PointField
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    """A foreign key model."""

    name = models.CharField(max_length=200)

    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")

    def __str__(self):
        return self.name


class Place(models.Model):
    """Main model to demonstrate the WFS."""

    name = models.CharField(max_length=200)
    location = PointField()  # no srid, stored as WGS84

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    has_free_parking = models.BooleanField(null=True, blank=True)
    tags = ArrayField(base_field=models.CharField(max_length=100), null=True, blank=True)

    owners = models.ManyToManyField(
        User,
        related_name="places",
        limit_choices_to={"is_active": True},
        blank=True,
    )

    created = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Place")
        verbose_name_plural = _("Places")

    def __str__(self):
        return self.name


class OpeningHour(models.Model):
    """A foreign model, using a reverse relation"""

    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="opening_hours")
    # 1 = mon, 7 = sun.
    weekday = models.IntegerField(choices=list(enumerate(calendar.day_name, start=1)))
    start_time = models.TimeField(default=time(16, 0))
    end_time = models.TimeField(default=time(23, 30))

    class Meta:
        ordering = ("weekday", "start_time")
        verbose_name = _("Opening Hour")
        verbose_name_plural = _("Opening Hours")

    def __str__(self):
        return f"{self.get_weekday_display()}: {self.start_time} - {self.end_time}"
