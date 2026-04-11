import json

from django.conf import settings
from django.contrib.gis.measure import D
from django.core.mail import send_mail
from django.template.loader import render_to_string

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


# ---------------------------------------------------------------------------
# Badge award helpers (Phase 5E)
# ---------------------------------------------------------------------------

_BADGE_DEFS = [
    ("first-cleanup",   "First Cleanup",    "Submitted your first cleanup proof.",          "🧹"),
    ("five-cleanups",   "5 Cleanups",       "Submitted 5 cleanup proofs.",                  "⭐"),
    ("twenty-cleanups", "20 Cleanups",      "Submitted 20 cleanup proofs.",                 "🏆"),
    ("hazard-reporter", "Hazard Reporter",  "Reported a site with a hazard flag.",           "⚠️"),
    ("repeat-cleaner",  "Repeat Cleaner",   "Cleaned the same site more than once.",         "♻️"),
    ("team-founder",    "Team Founder",     "Created a community team.",                     "🤝"),
    ("event-organizer", "Event Organizer",  "Organised a community cleanup event.",          "📅"),
]


def _ensure_badges():
    """Idempotently create the built-in badge records."""
    from .models import Badge
    for slug, name, description, icon in _BADGE_DEFS:
        Badge.objects.get_or_create(slug=slug, defaults={"name": name, "description": description, "icon": icon})


def _award(user, badge_slug):
    """Award a badge to a user if they don't already hold it. Returns True if newly awarded."""
    from .models import Badge, UserBadge
    try:
        badge = Badge.objects.get(slug=badge_slug)
    except Badge.DoesNotExist:
        return False
    ub, created = UserBadge.objects.get_or_create(user=user, badge=badge)
    if created and user.email:
        try:
            body = render_to_string("email/badge_awarded.html", {"user": user, "badge": badge})
            send_mail(
                subject=f"You earned the {badge.name} badge on UC CleanUp!",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            pass
    return created


def check_and_award_badges(user):
    """Check all badge conditions for a user and award any newly earned badges."""
    from .models import CleanupProof, TrashSite
    try:
        proof_count = CleanupProof.objects.filter(created_by=user).count()
        if proof_count >= 1:
            _award(user, "first-cleanup")
        if proof_count >= 5:
            _award(user, "five-cleanups")
        if proof_count >= 20:
            _award(user, "twenty-cleanups")

        if TrashSite.objects.filter(created_by=user, hazard_flag=True).exists():
            _award(user, "hazard-reporter")

        # Repeat cleaner: cleaned a site where they previously submitted a proof
        site_ids_cleaned = set(
            CleanupProof.objects.filter(created_by=user, trash_site__isnull=False)
            .values_list("trash_site_id", flat=True)
        )
        if len([s for s in site_ids_cleaned if CleanupProof.objects.filter(created_by=user, trash_site_id=s).count() > 1]):
            _award(user, "repeat-cleaner")

        from .models import Team, CleanupEvent
        if Team.objects.filter(leader=user).exists():
            _award(user, "team-founder")
        if CleanupEvent.objects.filter(organizer=user).exists():
            _award(user, "event-organizer")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Cron job recorder (Phase 5B)
# ---------------------------------------------------------------------------

def record_job_run(job_name, success, error=""):
    """Update ScheduledJobLog for the given job."""
    from .models import ScheduledJobLog
    from django.utils import timezone
    log, _ = ScheduledJobLog.objects.get_or_create(job_name=job_name)
    log.last_run_at = timezone.now()
    log.last_status = "ok" if success else "error"
    if success:
        log.last_success_at = timezone.now()
    if error:
        log.last_error = error[:2000]
    elif success:
        log.last_error = ""
    log.save()
