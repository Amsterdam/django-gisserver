"""The URL patterns for the example app."""

import places.urls
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def _root_view(request):
    return HttpResponse(
        """
        <title>django-gisserver demo app</title>
        <style>body { line-height: 1.5; font-family: Arial, sans-serif; }</style>
        <body>
          <h1>Demo of django-gisserver</h1>
          <ul>
            <li><a href="/admin/">Django Admin</a></li>
            <li><a href="/wfs/">WFS Server</a></li>
          </ul>
        </body>
        """
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("wfs/", include(places.urls)),
    path("", _root_view),
]
