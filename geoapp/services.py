from .models import ActivityLog, District


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


def assign_district(point):
    """Return the first active District whose geometry contains the given point, or None."""
    return District.objects.filter(geometry__covers=point, active=True).first()
