from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("map/", views.map_view, name="map"),
    path("updates/", views.updates_view, name="updates"),
    path("impact/", views.impact_view, name="impact"),
    path("api/activity/", views.activity_api, name="api_activity"),
    path("api/feedback/", views.feedback_create_api, name="api_feedback_create"),
    path("api/features/", views.features_api, name="api_features"),
    path("api/trash-sites/", views.trash_site_create_api, name="api_trash_site_create"),
    path("api/trash-sites/<uuid:site_id>/", views.trash_site_update_api, name="api_trash_site_update"),
    path("api/trash-sites/<uuid:site_id>/detail/", views.trash_site_detail_api, name="api_trash_site_detail"),
    path("api/trash-sites/<uuid:site_id>/mark-cleaned/", views.trash_site_mark_cleaned_api, name="api_trash_site_mark_cleaned"),
    path("api/route-cleanups/", views.route_cleanup_create_api, name="api_route_cleanup_create"),
    path("api/route-cleanups/<uuid:route_id>/", views.route_cleanup_detail_api, name="api_route_cleanup_detail_root"),
    path("api/route-cleanups/<uuid:route_id>/detail/", views.route_cleanup_detail_api, name="api_route_cleanup_detail"),
]
