from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import ActivityLog, CleanupProof, FeedbackEntry, Photo, Profile, RouteCleanup, TrashSite


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


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "created_at", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("activity_type", "actor", "trash_site", "route_cleanup", "created_at")
    list_filter = ("activity_type",)
    search_fields = ("summary", "actor__username")
    autocomplete_fields = ("actor", "trash_site", "route_cleanup", "proof")
    readonly_fields = ("created_at",)


@admin.register(FeedbackEntry)
class FeedbackEntryAdmin(admin.ModelAdmin):
    list_display = ("feedback_type", "status", "created_by", "created_at")
    list_filter = ("feedback_type", "status")
    search_fields = ("message", "created_by__username", "page_url")
    autocomplete_fields = ("created_by",)
    readonly_fields = ("created_at", "updated_at")
