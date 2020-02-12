from django.contrib.gis.db.models import PointField
from django.db import models


class Restaurant(models.Model):
    name = models.CharField(max_length=200)
    location = PointField(null=True)

    def __str__(self):
        return self.name
