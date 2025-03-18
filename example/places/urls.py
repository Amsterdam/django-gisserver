from django.urls import path

from . import views

urlpatterns = [
    path("", views.PlacesWFSView.as_view(), name="places-wfs"),
]
