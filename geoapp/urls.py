from django.urls import path

from . import views

urlpatterns = [
    # Public HTML
    path("", views.map_view, name="map"),
    path("cleanups/", views.cleanups_view, name="cleanups"),
    path("about/", views.about_view, name="about"),
    path("healthz", views.healthz, name="healthz"),
    path("profile/", views.profile_view, name="profile"),
    path("leaderboard/", views.leaderboard_view, name="leaderboard"),
    path("events/", views.events_view, name="events"),
    path("teams/", views.teams_list_view, name="teams"),
    path("teams/<slug:team_slug>/", views.team_view, name="team"),
    path("teams/<slug:team_slug>/certificate/", views.team_certificate_view, name="team_certificate"),
    path("sw.js", views.service_worker_view, name="service_worker"),

    # Public JSON API
    path("api/features/", views.features_api, name="api_features"),
    path("api/districts/", views.districts_api, name="api_districts"),
    path("api/impact/", views.impact_api, name="api_impact"),
    path("api/heatmap/", views.heatmap_api, name="api_heatmap"),
    path("api/leaderboard/", views.leaderboard_api, name="api_leaderboard"),
    path("api/events/", views.events_list_api, name="api_events_list"),
    path("api/events/<uuid:event_id>/", views.event_detail_api, name="api_event_detail"),
    path("api/events/<uuid:event_id>/rsvp/", views.event_rsvp_api, name="api_event_rsvp"),
    path("api/events/<uuid:event_id>/complete/", views.event_complete_api, name="api_event_complete"),
    path("api/trash-sites/<uuid:site_id>/detail/", views.trash_site_detail_api, name="api_trash_site_detail"),
    path("api/cleanups/", views.cleanups_list_api, name="api_cleanups_list"),
    path("api/teams/", views.team_list_api, name="api_teams_list"),
    path("api/teams/<slug:team_slug>/", views.team_detail_api, name="api_team_detail"),
    path("api/push/vapid-key/", views.push_vapid_key_api, name="api_push_vapid_key"),
    path("share/<uuid:site_id>/", views.share_view, name="share_site"),

    # Authenticated JSON API
    path("api/preferences/", views.preferences_api, name="api_preferences"),
    path("api/trash-sites/", views.trash_site_create_api, name="api_trash_site_create"),
    path("api/trash-sites/<uuid:site_id>/", views.trash_site_update_api, name="api_trash_site_update"),
    path("api/trash-sites/<uuid:site_id>/mark-cleaned/", views.trash_site_mark_cleaned_api, name="api_trash_site_mark_cleaned"),
    path("api/trash-sites/<uuid:site_id>/verify/", views.trash_site_verify_api, name="api_trash_site_verify"),
    path("api/teams/<slug:team_slug>/join/", views.team_join_api, name="api_team_join"),
    path("api/push/subscribe/", views.push_subscribe_api, name="api_push_subscribe"),
    path("api/push/unsubscribe/", views.push_unsubscribe_api, name="api_push_unsubscribe"),
    path("api/feedback/", views.feedback_create_api, name="api_feedback_create"),
]
