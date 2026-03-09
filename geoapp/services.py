from django.db.models import Sum

from .models import ActivityLog, CleanupProof, RouteCleanup, TrashSite


def log_activity(activity_type, actor, trash_site=None, route_cleanup=None, proof=None, summary=""):
    if not actor or not actor.is_authenticated:
        return None
    return ActivityLog.objects.create(
        activity_type=activity_type,
        actor=actor,
        trash_site=trash_site,
        route_cleanup=route_cleanup,
        proof=proof,
        summary=summary[:255],
    )


def build_user_impact_stats(user):
    cleanup_proofs = CleanupProof.objects.filter(created_by=user, trash_site__isnull=False)
    route_qs = RouteCleanup.objects.filter(created_by=user)
    cleaned_site_ids = cleanup_proofs.values_list("trash_site_id", flat=True)

    totals = cleanup_proofs.aggregate(total_bags=Sum("bags_count"))
    route_totals = route_qs.aggregate(
        total_distance=Sum("distance_miles"),
        total_time=Sum("time_spent_minutes"),
    )

    return {
        "reported_sites": TrashSite.objects.filter(created_by=user).count(),
        "cleaned_sites": TrashSite.objects.filter(id__in=cleaned_site_ids).distinct().count(),
        "logged_routes": route_qs.count(),
        "bags_collected": totals["total_bags"] or 0,
        "route_miles": float(route_totals["total_distance"] or 0.0),
        "time_spent_minutes": route_totals["total_time"] or 0,
    }
