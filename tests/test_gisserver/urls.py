from django.urls import path

from . import views

urlpatterns = [
    path("v1/wfs/", views.PlacesWFSView.as_view(), name="wfs-view"),
    path(
        "v1/wfs-complextypes/",
        views.ComplexTypesWFSView.as_view(),
        name="wfs-view-complextypes",
    ),
    path(
        "v1/wfs-flattened/",
        views.FlattenedWFSView.as_view(),
        name="wfs-view-flattened",
    ),
]
