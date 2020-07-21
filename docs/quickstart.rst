Getting started
===============

The django-gisserver module is designed to be used in an existing GeoDjango project.
Hence, all configuration is done in code.

Suppose the project has this exisiting GeoDjango model:

.. code-block:: python

    from django.contrib.gis.db.models import PointField
    from django.db import models


    class Restaurant(models.Model):
        name = models.CharField(max_length=200)
        location = PointField(null=True)

        def __str__(self):
            return self.name

...then, the WFS logic can be exposed by writing a view.

.. code-block:: python

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

.. note::
    The list of ``feature_types`` lists all models that are exposed by this single view.
    Typically, a WFS server exposes a collection of related features on a single endpoint.

Use that view in the URLConf:

.. code-block:: python

    from django.urls import path
    from . import views

    urlpatterns = [
        path("/wfs/places/", views.PlacesWFSView.as_view()),
    ]

Testing the server
------------------

You can now use http://localhost:8000/wfs/places/ in your GIS application.
It will perform requests such as:

* http://localhost:8000/wfs/places/?SERVICE=WFS&REQUEST=GetCapabilities&ACCEPTVERSIONS=2.0.0,1.1.0,1.0.0
* http://localhost:8000/wfs/places/?SERVICE=WFS&REQUEST=DescribeFeatureType&VERSION=2.0.0&TYPENAMES=restaurant
* http://localhost:8000/wfs/places/?SERVICE=WFS&REQUEST=GetFeature&VERSION=2.0.0&TYPENAMES=restaurant&STARTINDEX=0&COUNT=1000&SRSNAME=urn:ogc:def:crs:EPSG::28992

Specifying the output format
----------------------------

By adding ``&OUTPUTFORMAT=geojson`` or ``&OUTPUTFORMAT=csv`` to the ``GetFeature`` request,
the GeoJSON and CSV outputs are returned.
These formats have an unlimited page size by default, as they're quite efficient.
