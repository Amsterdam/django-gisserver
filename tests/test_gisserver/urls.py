from django.urls import path

from .views import PlacesWFSView

urlpatterns = [
    path("v1/wfs/", PlacesWFSView.as_view(), name="wfs-view"),
]
