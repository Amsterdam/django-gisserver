import calendar
from datetime import datetime, time, timezone

from django.contrib.gis.db.models import PointField
from django.contrib.postgres.fields import ArrayField
from django.db import models


def current_datetime():
    return datetime(2020, 4, 5, 12, 11, 10, 0, tzinfo=timezone.utc)


class City(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class OpeningHour(models.Model):
    # 0 = mon, 6 = sun.
    weekday = models.IntegerField(choices=list(enumerate(calendar.day_name)))
    start_time = models.TimeField(default=time(16, 0))
    end_time = models.TimeField(default=time(23, 30))


class Restaurant(models.Model):
    name = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True)
    location = PointField(null=True)  # no srid, stored as WGS84
    rating = models.FloatField(default=0)
    is_open = models.BooleanField(default=False)
    created = models.DateTimeField(default=current_datetime)

    opening_hours = models.ManyToManyField(OpeningHour)
    tags = ArrayField(base_field=models.CharField(max_length=100), null=True)

    def __str__(self):
        return self.name
