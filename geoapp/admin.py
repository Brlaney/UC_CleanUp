from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import CleanupProof, Photo, RouteCleanup, TrashSite


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0


@admin.register(CleanupProof)
class CleanupProofAdmin(admin.ModelAdmin):
    list_display = ("id", "trash_site", "route_cleanup", "bags_count", "created_by", "created_at")
    search_fields = ("id", "note", "created_by__username")
    inlines = [PhotoInline]


@admin.register(TrashSite)
class TrashSiteAdmin(GISModelAdmin):
    list_display = ("id", "status", "severity", "hazard_flag", "created_by", "created_at", "cleaned_at")
    list_filter = ("status", "severity", "hazard_flag")
    search_fields = ("title", "description", "created_by__username")
    readonly_fields = ("created_at", "updated_at", "cleaned_at")
    autocomplete_fields = ("created_by", "claimed_by")


@admin.register(RouteCleanup)
class RouteCleanupAdmin(GISModelAdmin):
    list_display = ("id", "status", "distance_miles", "time_spent_minutes", "created_by", "created_at")
    list_filter = ("status",)
    search_fields = ("notes", "created_by__username")
    readonly_fields = ("distance_miles", "created_at")
    autocomplete_fields = ("created_by",)


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "proof", "created_at")
    autocomplete_fields = ("proof",)
