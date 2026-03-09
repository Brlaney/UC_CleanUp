import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import LineString, Point
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from geoapp.models import ActivityLog, CleanupProof, FeedbackEntry, Profile, RouteCleanup, TrashSite
from geoapp.services import log_activity


class Command(BaseCommand):
    help = "Seed deterministic demo content for Playwright screenshot capture."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="screenshot_demo")
        parser.add_argument("--password", default="screenshot_demo_pass_123")
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete and recreate demo records owned by the screenshot user.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the seeded identifiers as JSON for automation.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        reset = options["reset"]
        json_output = options["json"]

        user_model = get_user_model()
        user, _created = user_model.objects.get_or_create(
            username=username,
            defaults={"is_active": True},
        )
        user.is_active = True
        user.set_password(password)
        user.save(update_fields=["is_active", "password"])
        Profile.objects.get_or_create(user=user)

        if reset:
            self._clear_existing_demo_state(user)

        payload = self._seed_demo_content(user, password)

        if json_output:
            self.stdout.write(json.dumps(payload))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded screenshot demo data for user "
                f"'{payload['username']}' with pending site {payload['pending_site_id']} "
                f"and route {payload['route_id']}."
            )
        )

    def _clear_existing_demo_state(self, user):
        ActivityLog.objects.filter(actor=user).delete()
        FeedbackEntry.objects.filter(created_by=user).delete()
        CleanupProof.objects.filter(created_by=user).delete()
        RouteCleanup.objects.filter(created_by=user).delete()
        TrashSite.objects.filter(created_by=user).delete()

    def _seed_demo_content(self, user, password):
        now = timezone.now()

        pending_site = TrashSite.objects.create(
            title="Screenshot Demo Pending Site",
            description="Roadside litter near the greenway entrance.",
            severity=TrashSite.Severity.MEDIUM,
            hazard_flag=True,
            status=TrashSite.Status.PENDING,
            location=Point(-85.5016, 36.1627, srid=4326),
            created_by=user,
        )
        TrashSite.objects.filter(pk=pending_site.pk).update(
            created_at=now - timedelta(days=2, hours=2),
            updated_at=now - timedelta(days=2, hours=2),
        )
        pending_site.refresh_from_db()

        cleaned_site = TrashSite.objects.create(
            title="Screenshot Demo Cleaned Site",
            description="Trailhead cleanup completed with bagged litter removed.",
            severity=TrashSite.Severity.HEAVY,
            hazard_flag=False,
            status=TrashSite.Status.CLEANED,
            location=Point(-85.4925, 36.1662, srid=4326),
            cleaned_at=now - timedelta(hours=18),
            created_by=user,
        )
        TrashSite.objects.filter(pk=cleaned_site.pk).update(
            created_at=now - timedelta(days=1, hours=6),
            updated_at=now - timedelta(hours=18),
            cleaned_at=now - timedelta(hours=18),
        )
        cleaned_site.refresh_from_db()

        proof = CleanupProof.objects.create(
            trash_site=cleaned_site,
            note="Collected cans and bagged roadside trash.",
            bags_count=3,
            created_by=user,
        )
        CleanupProof.objects.filter(pk=proof.pk).update(created_at=now - timedelta(hours=17))
        proof.refresh_from_db()

        route = RouteCleanup.objects.create(
            geometry=LineString(
                (-85.5070, 36.1590),
                (-85.5025, 36.1612),
                (-85.4975, 36.1648),
                srid=4326,
            ),
            notes="Screenshot demo route along the Cookeville roadside shoulder.",
            time_spent_minutes=42,
            created_by=user,
        )
        RouteCleanup.objects.filter(pk=route.pk).update(created_at=now - timedelta(hours=4))
        route.refresh_from_db()

        self._reset_activity_log(user)
        self._create_activity(
            activity_type=ActivityLog.ActivityType.TRASH_REPORTED,
            actor=user,
            trash_site=pending_site,
            summary="Screenshot demo: Added a pending roadside litter report.",
            created_at=now - timedelta(days=2, hours=1),
        )
        self._create_activity(
            activity_type=ActivityLog.ActivityType.TRASH_REPORTED,
            actor=user,
            trash_site=cleaned_site,
            summary="Screenshot demo: Added a cleanup report at the trailhead.",
            created_at=now - timedelta(days=1, hours=5),
        )
        self._create_activity(
            activity_type=ActivityLog.ActivityType.TRASH_CLEANED,
            actor=user,
            trash_site=cleaned_site,
            proof=proof,
            summary="Screenshot demo: Marked the trailhead site cleaned with proof.",
            created_at=now - timedelta(hours=17),
        )
        self._create_activity(
            activity_type=ActivityLog.ActivityType.ROUTE_LOGGED,
            actor=user,
            route_cleanup=route,
            summary="Screenshot demo: Logged a roadside cleanup route.",
            created_at=now - timedelta(hours=3),
        )

        return {
            "username": user.username,
            "password": password,
            "pending_site_id": str(pending_site.id),
            "cleaned_site_id": str(cleaned_site.id),
            "route_id": str(route.id),
        }

    def _reset_activity_log(self, user):
        ActivityLog.objects.filter(actor=user).delete()

    def _create_activity(self, activity_type, actor, summary, created_at, trash_site=None, route_cleanup=None, proof=None):
        activity = log_activity(
            activity_type=activity_type,
            actor=actor,
            trash_site=trash_site,
            route_cleanup=route_cleanup,
            proof=proof,
            summary=summary,
        )
        ActivityLog.objects.filter(pk=activity.pk).update(created_at=created_at)
