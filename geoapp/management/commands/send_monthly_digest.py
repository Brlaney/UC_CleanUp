from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.measure import D
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from geoapp.models import CleanupEvent, CleanupProof, PushSubscription, TrashSite
from geoapp.services import record_job_run

User = get_user_model()
JOB_NAME = "send_monthly_digest"


class Command(BaseCommand):
    help = "Send a monthly neighbourhood digest email to users with saved locations."

    def handle(self, *args, **options):
        try:
            self._run()
            record_job_run(JOB_NAME, success=True)
        except Exception as exc:
            record_job_run(JOB_NAME, success=False, error=str(exc))
            raise

    def _run(self):
        now = timezone.now()
        month_ago = now - timedelta(days=30)
        two_months_ago = now - timedelta(days=60)

        # Users with saved push-subscription locations who have an email address
        subs = (
            PushSubscription.objects
            .filter(saved_location__isnull=False, user__isnull=False)
            .select_related("user")
        )

        sent = 0
        for sub in subs:
            user = sub.user
            if not user or not user.email:
                continue

            radius = sub.notification_radius_miles or 2.0
            location = sub.saved_location

            nearby_new = (
                TrashSite.objects
                .filter(location__dwithin=(location, D(mi=radius)), created_at__gte=month_ago)
                .count()
            )

            upcoming_events = list(
                CleanupEvent.objects
                .filter(
                    location__dwithin=(location, D(mi=radius * 5)),
                    status=CleanupEvent.Status.SCHEDULED,
                    event_date__gte=now,
                )
                .order_by("event_date")[:3]
            )

            this_month_cleanups = CleanupProof.objects.filter(
                created_by=user, created_at__gte=month_ago
            ).count()
            last_month_cleanups = CleanupProof.objects.filter(
                created_by=user, created_at__gte=two_months_ago, created_at__lt=month_ago
            ).count()

            if nearby_new == 0 and not upcoming_events and this_month_cleanups == 0:
                continue

            body = render_to_string("email/monthly_digest.html", {
                "user": user,
                "nearby_new": nearby_new,
                "upcoming_events": upcoming_events,
                "this_month_cleanups": this_month_cleanups,
                "last_month_cleanups": last_month_cleanups,
                "radius_miles": int(radius),
                "report_date": now,
            })

            send_mail(
                subject=f"Your UC CleanUp Monthly Update — {now.strftime('%B %Y')}",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Sent monthly digest to {sent} user(s)."))
