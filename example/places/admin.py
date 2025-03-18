from django.contrib import admin

from . import models


@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin for categories"""


class OpeningHourInline(admin.TabularInline):
    model = models.OpeningHour


@admin.register(models.Place)
class PlaceAdmin(admin.ModelAdmin):
    """Admin for restaurants"""

    list_display = ("name", "category", "tags")
    list_filter = ("category",)
    list_select_related = ("category",)
    inlines = [OpeningHourInline]
    filter_horizontal = ("owners",)
