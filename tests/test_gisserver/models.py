from datetime import datetime

from django.contrib.gis.db.models import PointField
from django.db import models
from django.utils.timezone import utc


def current_datetime():
    return datetime(2020, 4, 5, 12, 11, 10, 0, tzinfo=utc)


class City(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class Restaurant(models.Model):
    name = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True)
    location = PointField(null=True)
    rating = models.FloatField(default=0)
    created = models.DateTimeField(default=current_datetime)

    def __str__(self):
        return self.name
