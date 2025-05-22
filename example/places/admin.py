from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin  # Uses OSM tiles instead of NASA map

from . import models


@admin.register(models.Province)
class ProvinceAdmin(admin.ModelAdmin):
    """Admin for provinces"""

    list_display = ("name",)
    list_filter = ("name",)


@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin for categories"""


class OpeningHourInline(admin.TabularInline):
    model = models.OpeningHour


@admin.register(models.Place)
class PlaceAdmin(GISModelAdmin):
    """Admin for restaurants"""

    list_display = ("name", "category", "tags")
    list_filter = ("category",)
    list_select_related = ("category",)
    inlines = [OpeningHourInline]
    filter_horizontal = ("owners",)
    # gis_widget_kwargs = {"attrs": {"display_raw": True}}
