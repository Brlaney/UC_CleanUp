from django.urls import path

from . import views

urlpatterns = [
    # Public HTML
    path("", views.map_view, name="map"),
    path("cleanups/", views.cleanups_view, name="cleanups"),
    path("healthz", views.healthz, name="healthz"),

    # Public JSON API
    path("api/features/", views.features_api, name="api_features"),
    path("api/districts/", views.districts_api, name="api_districts"),
    path("api/trash-sites/<uuid:site_id>/detail/", views.trash_site_detail_api, name="api_trash_site_detail"),
    path("api/cleanups/", views.cleanups_list_api, name="api_cleanups_list"),

    # Authenticated JSON API
    path("api/trash-sites/", views.trash_site_create_api, name="api_trash_site_create"),
    path("api/trash-sites/<uuid:site_id>/", views.trash_site_update_api, name="api_trash_site_update"),
    path("api/trash-sites/<uuid:site_id>/mark-cleaned/", views.trash_site_mark_cleaned_api, name="api_trash_site_mark_cleaned"),
    path("api/feedback/", views.feedback_create_api, name="api_feedback_create"),
]
