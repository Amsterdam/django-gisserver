"""The URL patterns for the example app."""

import places.urls
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def _root_view(request):
    return HttpResponse(
        """<!doctype html>
        <html><head>
          <title>django-gisserver demo app</title>
          <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.6/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-4Q6Gf2aSP4eDXB8Miphtr37CMZZQ5oXLH2yaXMJ2w8e2ZtHTl7GptT4jmndRuHDT" crossorigin="anonymous">
          <style> body { margin: 2rem; } </style>
        </head>
        <body>
          <h1>Demo of django-gisserver</h1>
          <ul>
            <li><a href="/admin/">Django Admin</a></li>
            <li><a href="/wfs/">WFS Server</a></li>
          </ul>
        </body>
        </html>
        """
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("wfs/", include(places.urls)),
    path("", _root_view),
]
