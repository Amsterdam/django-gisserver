[![Documentation](https://readthedocs.org/projects/django-gisserver/badge/?version=latest)](https://django-gisserver.readthedocs.io/en/latest/?badge=latest)
[![Travis](https://img.shields.io/travis/amsterdam/django-gisserver.svg)](http://travis-ci.org/amsterdam/django-gisserver)
[![PyPI](https://img.shields.io/pypi/v/django-gisserver.svg)](https://pypi.python.org/pypi/django-gisserver)
[![MPL License](https://img.shields.io/badge/license-MPL%202.0-blue.svg)](https://pypi.python.org/pypi/django-gisserver)
[![Coverage](https://img.shields.io/codecov/c/github/amsterdam/django-gisserver/master.svg)](https://codecov.io/github/amsterdam/django-gisserver?branch=master)

# django-gisserver

Django speaking WFS 2.0 to expose geo data.

## Features

* WFS 2.0 Basic implementation.
* GML 3.2 output.
* Standard and spatial filtering (FES 2.0)
* GeoJSON and CSV export formats.
* Extensible view/operations.
* Uses GeoDjango queries for filtering.
* Streaming responses for large datasets.

## Documentation

For more details, see: <https://django-gisserver.readthedocs.io/>


## Quickstart

Install the module in your project:

```bash
pip install django-gisserver
```

Add it to the ``INSTALLED_APPS``:

```python
INSTALLED_APPS = [
    ...
    "gisserver",
]
```

Create a model that exposes a GeoDjango field:

```python
from django.contrib.gis.db.models import PointField
from django.db import models


class Restaurant(models.Model):
    name = models.CharField(max_length=200)
    location = PointField(null=True)

    def __str__(self):
        return self.name
```

Write a view that exposes this model as a WFS feature:

```python
from gisserver.features import FeatureType, ServiceDescription
from gisserver.geometries import CRS, WGS84
from gisserver.views import WFSView
from .models import Restaurant

RD_NEW = CRS.from_srid(28992)


class PlacesWFSView(WFSView):
    """An simple view that uses the WFSView against our test model."""

    xml_namespace = "http://example.org/gisserver"

    # The service metadata
    service_description = ServiceDescription(
        title="Places",
        abstract="Unittesting",
        keywords=["django-gisserver"],
        provider_name="Django",
        provider_site="https://www.example.com/",
        contact_person="django-gisserver",
    )

    # Each Django model is listed here as a feature.
    feature_types = [
        FeatureType(
            Restaurant.objects.all(),
            fields="__all__",
            other_crs=[RD_NEW]
        ),
    ]
```

Use that view in the URLConf:

```python
from django.urls import path
from . import views

urlpatterns = [
    path("/wfs/places/", views.PlacesWFSView.as_view()),
]
```

You can now use http://localhost:8000/wfs/places/ in your GIS application.
It will perform requests such as:

* <http://localhost:8000/wfs/places/?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=2.0.0,1.1.0,1.0.0>
* <http://localhost:8000/wfs/places/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=restaurant>
* <http://localhost:8000/wfs/places/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant&STARTINDEX=0&COUNT=1000&SRSNAME=urn:ogc:def:crs:EPSG::28992>

By adding `&OUTPUTFORMAT=geojson` or `&OUTPUTFORMAT=csv` to the `GetFeature` request, the GeoJSON and CSV outputs are returned.
The CSV output has an unlimited page size, as it's quite performant.



## Why this code is shared

The "datapunt" team of the Municipality of Amsterdam develops software for the municipality.
Much of this software is then published as Open Source so that other municipalities,
organizations and citizens can use the software as a basis and inspiration to develop
similar software themselves. The Municipality of Amsterdam considers it important that
software developed with public money is also publicly available.

This package is initially developed by the City of Amsterdam, but the tools
and concepts created in this project can be used in any city.
