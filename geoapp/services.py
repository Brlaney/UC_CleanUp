import json

from django.conf import settings
from django.contrib.gis.measure import D

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


def notify_nearby_subscribers(trash_site):
    if not (getattr(settings, "VAPID_PRIVATE_KEY", "") and getattr(settings, "VAPID_PUBLIC_KEY", "")):
        return
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return

    from .models import PushSubscription
    subs = list(PushSubscription.objects.filter(saved_location__isnull=False))
    if not subs:
        return

    payload = json.dumps({
        "title": "New trash report nearby",
        "body": trash_site.title or "A new site was reported near your saved location.",
        "url": "/?focus_id=" + str(trash_site.id),
    })

    for sub in subs:
        nearby = PushSubscription.objects.filter(
            pk=sub.pk,
            saved_location__dwithin=(trash_site.location, D(mi=sub.notification_radius_miles))
        ).exists()
        if not nearby:
            continue
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth_key},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_EMAIL},
            )
        except Exception:
            sub.delete()
