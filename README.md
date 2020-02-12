# django-gisserver

Django speaking WFS 2.0 to expose geo data.

## Features

* WFS 2.0 simple implementation.
* GML 3.2 output.
* GeoJSON export support.
* Extensible view/operations.
* Uses GeoDjango queries for filtering.
* Uses Django template engine for rendering XML (might become streaming lxml later).

## Usage

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
from gisserver.types import CRS, WGS84
from gisserver.views import WFSView
from .models import Restaurant

RD_NEW = CRS.from_string("urn:ogc:def:crs:EPSG::28992")


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
        FeatureType(Restaurant.objects.all(), other_crs=[RD_NEW]),
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

By adding `&OUTPUTFORMAT=geojson` to the `GetFeature` request, the GeoJSON output is returned.

## Standards compliance

Currently, the following 3 methods are implemented:

* `GetCapabilities`
* `DescribeFeatureType`
* `GetFeature` with bbox and pagination support.

This is sufficient to show results in [QGis](https://qgis.org/).
The unit tests validate the output against WFS 2.0 XSD schema.

Some parts for conformance to the "WFS simple" level are not implemented yet:

* `GetPropertyValue`
* `ListStoredQueries`
* `DescribeStoredQueries`
* Certain parameters:
  * Filtering: `filter`, `filter_language`, `resourceID`, `propertyName`, `aliases`.
  * Remote resolving: `resolve`, `resolveDepth`, `resolveTimeout`.
  * Output rewriting: `namespaces`.
  * Some `GetCapabilities` features: `acceptFormats` and `sections`.
  * Using `GetFeature` with only the `StoredQuery` action.

Filtering is high on the TO-DO list.

### Low-prio items:

Anything outside WFS simple could be implemented, but is very low on the todo-list:

* The methods for the WFS basic, transactional, locking and inheritance conformance classes.
* HTTP POST requests.
* SOAP requests.
* Other protocols (WMS, WMTS, WCS)
* Other output formats (shapefile, CSV, KML, GML 3.1) - but easy to add.

## Development

When you follow the source of the `WFSView`, `WFSMethod` and `Parameter` classes,
you'll find that it's written with extensibility in mind. Extra parameters and operations
can easily be added there. You could even do that within your own projects and implementations.

The `Makefile` gives you all you need to start working on the project.
Typing `make` gives an overview of all possible shortcut commands.

The WFS specification and examples be found at:

* <http://portal.opengeospatial.org/files/?artifact_id=39967>
* <https://www.opengeospatial.org/standards/wfs#downloads>
* <http://schemas.opengis.net/wfs/2.0/>
* <https://mapserver.org/development/rfc/ms-rfc-105.html>


## Why this code is shared

The "datapunt" team of the Municipality of Amsterdam develops software for the municipality.
Much of this software is then published as Open Source so that other municipalities,
organizations and citizens can use the software as a basis and inspiration to develop
similar software themselves. The Municipality of Amsterdam considers it important that
software developed with public money is also publicly available.

This package is initially developed by the City of Amsterdam, but the tools
and concepts created in this project can be used in any city.
