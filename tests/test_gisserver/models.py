import calendar
from datetime import datetime, time, timezone

from django.contrib.gis.db.models import PointField
from django.contrib.gis.db.models.functions import Translate
from django.contrib.postgres.fields import ArrayField
from django.db import models


def current_datetime():
    return datetime(2020, 4, 5, 12, 11, 10, 0, tzinfo=timezone.utc)


class City(models.Model):
    name = models.CharField(max_length=200)
    region = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class OpeningHour(models.Model):
    # 0 = mon, 6 = sun.
    weekday = models.IntegerField(choices=list(enumerate(calendar.day_name)))
    start_time = models.TimeField(default=time(16, 0))
    end_time = models.TimeField(default=time(23, 30))

    class Meta:
        ordering = ("weekday",)

    def __str__(self):
        return f"{self.get_weekday_display()}: {self.start_time} - {self.end_time}"


class Restaurant(models.Model):
    name = models.CharField(max_length=200)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True)
    location = PointField(null=True)  # no srid, stored as WGS84
    rating = models.FloatField(default=0)
    is_open = models.BooleanField(default=False)
    created = models.DateTimeField(default=current_datetime)

    opening_hours = models.ManyToManyField(OpeningHour)
    tags = ArrayField(base_field=models.CharField(max_length=100), null=True)

    class Meta:
        ordering = ["id"]  # for test result consistency

    def __str__(self):
        return self.name


class RestaurantReview(models.Model):
    """A model whose geometry exists in another model.
    Can both be used to test reverse relations OR to test geometries on a related model.
    """

    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="reviews")
    review = models.TextField()

    def __str__(self):
        return f"{self.restaurant}: {self.review}"


if hasattr(models, "GeneratedField"):
    # Only available in Django 5 and later.

    class ModelWithGeneratedFields(models.Model):
        name = models.CharField(max_length=20)
        name_reversed = models.GeneratedField(
            expression=models.functions.Reverse("name"),
            output_field=models.CharField(max_length=20),
            db_persist=True,
        )

        geometry = PointField(null=True)

        geometry_translated = models.GeneratedField(
            expression=Translate("geometry", x=1, y=1),
            output_field=PointField(null=True),
            db_persist=True,
        )

        class Meta:
            ordering = ["id"]  # for test result consistency

        def __str__(self):
            return self.name
