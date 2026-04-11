from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from geoapp.models import CleanupEvent


class Command(BaseCommand):
    help = "Send reminder emails to RSVP'd attendees for events happening in the next 18–30 hours."

    def handle(self, *args, **options):
        now = timezone.now()
        window_start = now + timedelta(hours=18)
        window_end = now + timedelta(hours=30)

        events = CleanupEvent.objects.filter(
            status=CleanupEvent.Status.SCHEDULED,
            event_date__gte=window_start,
            event_date__lte=window_end,
        ).prefetch_related("rsvps__user")

        if not events.exists():
            self.stdout.write("No events in the 18–30h reminder window.")
            return

        sent = 0
        for event in events:
            attendee_count = event.rsvps.count()
            for rsvp in event.rsvps.all():
                email = None
                if rsvp.user_id and rsvp.user and rsvp.user.email:
                    email = rsvp.user.email
                elif rsvp.email:
                    email = rsvp.email

                if not email:
                    continue

                subject = f"Reminder: {event.title} is tomorrow!"
                body = render_to_string("email/event_reminder.html", {
                    "event": event,
                    "attendee_count": attendee_count,
                })
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=True,
                )
                sent += 1

        self.stdout.write(self.style.SUCCESS(f"Sent {sent} reminder email(s) for {events.count()} event(s)."))
