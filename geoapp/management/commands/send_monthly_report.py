from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from geoapp.models import TrashSite
from geoapp.services import record_job_run

JOB_NAME = "send_monthly_report"


class Command(BaseCommand):
    help = "Email a tiered escalation report of chronic problem sites to district reps and officials."

    def handle(self, *args, **options):
        try:
            self._run()
            record_job_run(JOB_NAME, success=True)
        except Exception as exc:
            record_job_run(JOB_NAME, success=False, error=str(exc))
            raise

    def _run(self):
        rep_email = getattr(settings, "DISTRICT_REP_EMAIL", "")
        commissioner_email = getattr(settings, "COMMISSIONER_EMAIL", "")
        dpw_email = getattr(settings, "DPW_DIRECTOR_EMAIL", "")

        if not rep_email:
            self.stderr.write("DISTRICT_REP_EMAIL is not set. Skipping.")
            return

        now = timezone.now()
        tier1_cutoff = now - timedelta(days=90)
        tier2_cutoff = now - timedelta(days=180)
        tier3_cutoff = now - timedelta(days=365)

        base_qs = TrashSite.objects.filter(
            status__in=["PENDING", "IN_PROGRESS"]
        ).select_related("district", "created_by").order_by("-created_at")

        # Tier 3: 365+ days — flag as chronic and notify all three recipients
        tier3 = list(base_qs.filter(created_at__lte=tier3_cutoff))
        if tier3:
            tier3_ids = [s.pk for s in tier3]
            TrashSite.objects.filter(pk__in=tier3_ids).update(chronic_site=True)

        # Tier 2: 180–364 days
        tier2 = list(base_qs.filter(created_at__lte=tier2_cutoff, created_at__gt=tier3_cutoff))
        # Tier 1: 90–179 days
        tier1 = list(base_qs.filter(created_at__lte=tier1_cutoff, created_at__gt=tier2_cutoff))

        total = len(tier1) + len(tier2) + len(tier3)
        if total == 0:
            self.stdout.write("No problem sites found. Nothing to report.")
            return

        subject = f"UC CleanUp — Monthly Problem Sites Report ({now.strftime('%B %Y')})"
        body = render_to_string("email/monthly_report.html", {
            "tier1_sites": tier1,
            "tier2_sites": tier2,
            "tier3_sites": tier3,
            "report_date": now,
            "total": total,
        })

        # Tier 1: rep only
        # Tier 2+3: rep + commissioner + DPW
        escalation_recipients = [e for e in [commissioner_email, dpw_email] if e]
        recipients = [rep_email]

        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )

        if (tier2 or tier3) and escalation_recipients:
            send_mail(
                subject=subject + " [ESCALATED]",
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=escalation_recipients,
                fail_silently=False,
            )

        self.stdout.write(self.style.SUCCESS(
            f"Sent monthly report: {len(tier1)} tier-1, {len(tier2)} tier-2, {len(tier3)} tier-3 sites."
        ))
