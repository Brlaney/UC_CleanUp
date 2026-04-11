from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from geoapp.models import TrashSite


class Command(BaseCommand):
    help = "Email a report of chronic problem sites (PENDING/IN_PROGRESS for 90+ days) to the district rep."

    def handle(self, *args, **options):
        recipient = getattr(settings, "DISTRICT_REP_EMAIL", "")
        if not recipient:
            self.stderr.write("DISTRICT_REP_EMAIL is not set. Skipping.")
            return

        cutoff = timezone.now() - timedelta(days=90)
        sites = (
            TrashSite.objects
            .filter(status__in=["PENDING", "IN_PROGRESS"], created_at__lte=cutoff)
            .select_related("district", "created_by")
            .order_by("-created_at")
        )

        if not sites.exists():
            self.stdout.write("No chronic problem sites found. Nothing to report.")
            return

        subject = f"UC CleanUp — Monthly Persistent Problem Sites Report ({timezone.now().strftime('%B %Y')})"
        body = render_to_string("email/monthly_report.html", {
            "sites": sites,
            "report_date": timezone.now(),
            "site_count": sites.count(),
        })

        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f"Sent monthly report to {recipient} ({sites.count()} sites)."))
