"""Populate the LOCAL dev database with realistic demo content.

This is a *marketing / screenshot* seeder — it fills the map, leaderboard,
cleanups gallery, events, teams and challenges so the app looks like an active
community. It is LOCAL-ONLY by design and refuses to run against production.

Usage (inside Docker):
    docker compose run --rm web python manage.py seed_demo
    docker compose run --rm web python manage.py seed_demo --reset
    docker compose run --rm web python manage.py seed_demo --scale 2 --reset

All demo users are namespaced with the ``demo_`` username prefix and all demo
teams/challenges use a ``demo-`` slug prefix, so ``--reset`` can cleanly remove
only demo content and never touches real user data.
"""

import io
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import LineString, Point, Polygon
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from geoapp.models import (
    ActivityLog,
    Challenge,
    CleanupEvent,
    CleanupProof,
    District,
    EventRSVP,
    FeedbackEntry,
    Photo,
    Profile,
    RouteCleanup,
    Team,
    TeamMembership,
    TrashSite,
)
from geoapp.services import _ensure_badges, check_and_award_badges

DEMO_USER_PREFIX = "demo_"
DEMO_SLUG_PREFIX = "demo-"

# Fallback bounding box around the Upper Cumberland region (Cookeville / Putnam),
# used only if no districts have been seeded yet.
FALLBACK_BBOX = (-85.85, 35.95, -85.05, 36.50)  # (min_lng, min_lat, max_lng, max_lat)

FIRST_NAMES = [
    "Ava", "Liam", "Noah", "Emma", "Olivia", "Mason", "Sophia", "Jacob",
    "Isabella", "William", "Mia", "Ethan", "Charlotte", "James", "Amelia",
    "Benjamin", "Harper", "Lucas", "Evelyn", "Henry", "Abigail", "Alex",
    "Grace", "Daniel", "Chloe", "Owen", "Lily", "Wyatt", "Zoe", "Caleb",
    "Nora", "Eli", "Hazel", "Josiah", "Aria", "Levi", "Ellie", "Isaac",
    "Layla", "Gabriel",
]
LAST_NAMES = [
    "Bledsoe", "Carr", "Denton", "Frye", "Grimes", "Hale", "Judd", "Keeble",
    "Loftis", "Maddux", "Nunley", "Officer", "Pruett", "Qualls", "Ramsey",
    "Sliger", "Tinsley", "Underwood", "Vaden", "Whitson", "York", "Ziegler",
]

TEAM_SEED = [
    ("Cookeville High Key Club", Team.OrgType.SCHOOL),
    ("Tennessee Tech Green Society", Team.OrgType.SCHOOL),
    ("Putnam County Rotary", Team.OrgType.CIVIC),
    ("Upper Cumberland Trail Alliance", Team.OrgType.CIVIC),
    ("First Baptist Serve Team", Team.OrgType.CHURCH),
    ("Algood Community Church", Team.OrgType.CHURCH),
    ("Scout Troop 342", Team.OrgType.SCOUT),
    ("Cane Creek Neighbors", Team.OrgType.OTHER),
]

SITE_TITLES = [
    "Roadside litter along the shoulder", "Dumped tires near the culvert",
    "Fast-food trash at the trailhead", "Illegal dump site off the gravel road",
    "Plastic bottles in the drainage ditch", "Overflowing bin at the park",
    "Construction debris on the roadside", "Broken glass in the parking lot",
    "Litter cluster near the bridge", "Bags of household trash dumped",
    "Scattered cans along the greenway", "Blown litter against the fence line",
]
SITE_DESCRIPTIONS = [
    "Accumulated over the last few weeks — needs a cleanup crew.",
    "Visible from the road; safe pull-off nearby for volunteers.",
    "Recurring hot spot, gets bad after weekends.",
    "Mostly recyclables plus some bagged trash.",
    "Please bring gloves and grabbers; some sharp items.",
    "Small area, a couple of volunteers could clear it in an hour.",
]
EVENT_TITLES = [
    "Saturday Greenway Cleanup", "Roadside Sweep + Coffee",
    "Community Park Tidy-Up", "Trailhead Litter Blitz",
    "Neighborhood Cleanup Day", "River Access Cleanup",
    "Fall Litter Challenge Kickoff", "Adopt-a-Road Workday",
]
FEEDBACK_MESSAGES = [
    ("The before/after photos are awesome, love seeing the impact!", FeedbackEntry.FeedbackType.GENERAL),
    ("Could you add a way to filter cleanups by team?", FeedbackEntry.FeedbackType.REQUEST),
    ("The map pin didn't drop on my first tap on mobile.", FeedbackEntry.FeedbackType.BUG),
    ("Would love push alerts when a new dump shows up near me.", FeedbackEntry.FeedbackType.REQUEST),
    ("Signed my scout troop up — super easy, thanks!", FeedbackEntry.FeedbackType.GENERAL),
    ("Photo upload spun for a while on a big image.", FeedbackEntry.FeedbackType.BUG),
]
HAZARD_TYPES = ["sharps", "vape_device", "vape_pen", "other"]


class Command(BaseCommand):
    help = "Seed the LOCAL dev DB with realistic demo content for screenshots/marketing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scale", type=float, default=1.0,
            help="Multiplier for how much content to generate (default 1.0).",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete existing demo content (demo_ users, demo- teams/challenges) before seeding.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Allow running when DEBUG is False (still refuses if a prod DB host is detected).",
        )
        parser.add_argument(
            "--seed", type=int, default=42,
            help="RNG seed for reproducible output (default 42).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self._guard_environment(options["force"])

        self.rng = random.Random(options["seed"])
        scale = max(0.1, options["scale"])

        if options["reset"]:
            removed = self._reset_demo_data()
            self.stdout.write(self.style.WARNING(f"Reset: removed {removed} demo users and their content."))
        elif self._demo_exists():
            raise CommandError(
                "Demo data already present. Re-run with --reset to wipe and re-seed."
            )

        _ensure_badges()
        self.areas = self._load_areas()

        users = self._create_users(int(40 * scale))
        teams = self._create_teams(users)
        sites = self._create_sites(users, teams, int(120 * scale))
        self._create_proofs_and_cleanups(sites, users)
        self._create_routes(users, int(15 * scale))
        self._create_events(users, int(12 * scale))
        self._create_challenges()
        self._create_feedback(users, int(10 * scale))

        for user in users:
            check_and_award_badges(user)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded demo content: {len(users)} users, {len(teams)} teams, "
            f"{len(sites)} sites, {CleanupProof.objects.filter(created_by__in=users).count()} proofs, "
            f"{CleanupEvent.objects.filter(organizer__in=users).count()} events, "
            f"{Challenge.objects.filter(slug__startswith=DEMO_SLUG_PREFIX).count()} challenges."
        ))
        self.stdout.write("View it at http://localhost:8000 (log in as any demo_* user, password: demo-pass-123).")

    # ------------------------------------------------------------------ guards

    def _guard_environment(self, force):
        if not settings.DEBUG and not force:
            raise CommandError(
                "Refusing to seed demo data with DEBUG=False. This command is local-only. "
                "Pass --force only if you are certain this is a local/dev database."
            )
        db_host = (settings.DATABASES.get("default", {}).get("HOST") or "").lower()
        prod_markers = ("supabase", "render.com", "amazonaws", "neon.tech")
        if any(marker in db_host for marker in prod_markers):
            raise CommandError(
                f"Database host '{db_host}' looks like production. Refusing to seed. "
                "seed_demo is for local databases only."
            )

    # -------------------------------------------------------------- geo helpers

    def _load_areas(self):
        """Return a list of GEOS geometries to sample points within."""
        geoms = [d.geometry for d in District.objects.filter(active=True)]
        if geoms:
            return geoms
        self.stdout.write(self.style.WARNING(
            "No districts found — using a fallback region bbox. Run seed_district / "
            "fetch_districts first for district-accurate placement."
        ))
        min_lng, min_lat, max_lng, max_lat = FALLBACK_BBOX
        return [Polygon.from_bbox((min_lng, min_lat, max_lng, max_lat))]

    def _random_point(self):
        geom = self.rng.choice(self.areas)
        min_lng, min_lat, max_lng, max_lat = geom.extent
        for _ in range(200):
            p = Point(
                self.rng.uniform(min_lng, max_lng),
                self.rng.uniform(min_lat, max_lat),
                srid=4326,
            )
            if geom.contains(p):
                return p
        return geom.point_on_surface

    def _random_area(self, center):
        """A small polygon around a center point, for area-style reports."""
        d = 0.0025
        lng, lat = center.x, center.y
        return Polygon(
            ((lng - d, lat - d), (lng + d, lat - d), (lng + d, lat + d), (lng - d, lat + d), (lng - d, lat - d)),
            srid=4326,
        )

    def _random_line(self):
        start = self._random_point()
        pts = [(start.x, start.y)]
        for _ in range(self.rng.randint(2, 4)):
            lng, lat = pts[-1]
            pts.append((lng + self.rng.uniform(-0.004, 0.004), lat + self.rng.uniform(-0.004, 0.004)))
        return LineString(pts, srid=4326)

    def _days_ago(self, max_days):
        return timezone.now() - timedelta(
            days=self.rng.randint(0, max_days),
            hours=self.rng.randint(0, 23),
            minutes=self.rng.randint(0, 59),
        )

    def _placeholder_image(self, label, rgb):
        """Generate a small in-memory JPEG so galleries have real imagery
        without bundling external/copyrighted photos."""
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return None
        img = Image.new("RGB", (640, 480), rgb)
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 630, 470], outline=(255, 255, 255), width=4)
        draw.text((28, 210), f"UC CleanUp — {label}", fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return ContentFile(buf.getvalue(), name=f"demo_{label.lower()}_{self.rng.randint(1000, 9999)}.jpg")

    # ---------------------------------------------------------------- creators

    def _create_users(self, count):
        user_model = get_user_model()
        users = []
        used = set()
        # A few coordinators/admins for a realistic org, rest members.
        for i in range(count):
            first = self.rng.choice(FIRST_NAMES)
            last = self.rng.choice(LAST_NAMES)
            base = f"{DEMO_USER_PREFIX}{first.lower()}{last.lower()}"
            username = base
            n = 1
            while username in used or user_model.objects.filter(username=username).exists():
                n += 1
                username = f"{base}{n}"
            used.add(username)

            user = user_model.objects.create_user(
                username=username,
                email=f"{first.lower()}.{last.lower()}@example.com",
                password="demo-pass-123",
                first_name=first,
                last_name=last,
            )
            # Profile is auto-created by the post_save signal; update role/visibility.
            if i < 2:
                role = Profile.Role.ADMIN
            elif i < 8:
                role = Profile.Role.COORDINATOR
            else:
                role = Profile.Role.MEMBER
            Profile.objects.filter(user=user).update(role=role, public_profile=True)
            users.append(user)
        return users

    def _create_teams(self, users):
        teams = []
        leaders = users[:8]
        for idx, (name, org_type) in enumerate(TEAM_SEED):
            leader = leaders[idx % len(leaders)]
            team = Team.objects.create(
                name=name,
                slug=f"{DEMO_SLUG_PREFIX}{slugify(name)}",
                description=f"{name} organizes regular cleanups across the Upper Cumberland.",
                org_type=org_type,
                leader=leader,
                district=self._nearest_district(),
            )
            TeamMembership.objects.create(user=leader, team=team, role=TeamMembership.Role.LEADER)
            for member in self.rng.sample(users, self.rng.randint(3, 6)):
                if member == leader:
                    continue
                TeamMembership.objects.get_or_create(
                    user=member, team=team, defaults={"role": TeamMembership.Role.MEMBER}
                )
            teams.append(team)
        return teams

    def _nearest_district(self):
        d = District.objects.filter(active=True).order_by("?").first()
        return d

    def _create_sites(self, users, teams, count):
        statuses = (
            [TrashSite.Status.PENDING] * 5
            + [TrashSite.Status.IN_PROGRESS] * 2
            + [TrashSite.Status.CLEANED] * 6
            + [TrashSite.Status.INVALID] * 1
        )
        severities = [TrashSite.Severity.LIGHT, TrashSite.Severity.MEDIUM, TrashSite.Severity.HEAVY]
        sites = []
        for _ in range(count):
            point = self._random_point()
            status = self.rng.choice(statuses)
            is_hazard = self.rng.random() < 0.22
            hazard_types = self.rng.sample(HAZARD_TYPES, self.rng.randint(1, 2)) if is_hazard else []
            is_area = self.rng.random() < 0.15

            site = TrashSite.objects.create(
                title=self.rng.choice(SITE_TITLES),
                description=self.rng.choice(SITE_DESCRIPTIONS),
                severity=self.rng.choice(severities),
                hazard_flag=bool(hazard_types),
                hazard_types=hazard_types,
                chronic_site=self.rng.random() < 0.12,
                status=status,
                location=point,
                area=self._random_area(point) if is_area else None,
                district=self.assign_district(point),
                created_by=self.rng.choice(users),
                team=self.rng.choice(teams) if self.rng.random() < 0.4 else None,
            )
            created = self._days_ago(90)
            fields = {"created_at": created, "updated_at": created}
            if status == TrashSite.Status.CLEANED:
                fields["cleaned_at"] = created + timedelta(days=self.rng.randint(1, 10))
                fields["updated_at"] = fields["cleaned_at"]
            TrashSite.objects.filter(pk=site.pk).update(**fields)
            site.refresh_from_db()
            sites.append(site)

            self._log(
                ActivityLog.ActivityType.TRASH_REPORTED, site.created_by,
                trash_site=site, summary=f"Reported: {site.title}", when=created,
            )
        return sites

    def assign_district(self, point):
        return District.objects.filter(geometry__covers=point, active=True).first()

    def _create_proofs_and_cleanups(self, sites, users):
        cleaned = [s for s in sites if s.status == TrashSite.Status.CLEANED]
        # Weight cleanups toward a subset of "power volunteers" so the
        # leaderboard has a realistic ranked distribution rather than everyone
        # tied at ~1 cleanup.
        power = users[: max(3, len(users) // 5)]
        for site in cleaned:
            if self.rng.random() < 0.6:
                cleaner = self.rng.choice(power)
            else:
                cleaner = self.rng.choice(users)
            proof = CleanupProof.objects.create(
                trash_site=site,
                note=self.rng.choice([
                    "Bagged everything and hauled it to the transfer station.",
                    "Cleared the whole shoulder — filled several bags.",
                    "Removed litter and sorted recyclables.",
                    "Site is clear now; will keep an eye on it.",
                ]),
                bags_count=self.rng.randint(1, 8),
                created_by=cleaner,
                team=site.team,
            )
            when = site.cleaned_at or self._days_ago(60)
            CleanupProof.objects.filter(pk=proof.pk).update(created_at=when)

            before = self._placeholder_image("BEFORE", (120, 100, 70))
            after = self._placeholder_image("AFTER", (70, 130, 90))
            if before:
                Photo.objects.create(proof=proof, image=before, photo_type=Photo.PhotoType.BEFORE)
            if after:
                Photo.objects.create(proof=proof, image=after, photo_type=Photo.PhotoType.AFTER)

            self._log(
                ActivityLog.ActivityType.TRASH_CLEANED, cleaner,
                trash_site=site, proof=proof,
                summary=f"Cleaned: {site.title} ({proof.bags_count} bags)", when=when,
            )

    def _create_routes(self, users, count):
        for _ in range(count):
            route = RouteCleanup.objects.create(
                geometry=self._random_line(),
                notes=self.rng.choice([
                    "Roadside shoulder sweep.",
                    "Adopt-a-road segment cleanup.",
                    "Cleared the ditch line along the route.",
                ]),
                time_spent_minutes=self.rng.randint(20, 120),
                created_by=self.rng.choice(users),
            )
            when = self._days_ago(75)
            RouteCleanup.objects.filter(pk=route.pk).update(created_at=when)
            self._log(
                ActivityLog.ActivityType.ROUTE_LOGGED, route.created_by,
                route_cleanup=route, summary="Logged a roadside cleanup route.", when=when,
            )

    def _create_events(self, users, count):
        now = timezone.now()
        events = []
        for i in range(count):
            # Roughly half past (completed), half upcoming (scheduled).
            if i < count // 2:
                event_date = now - timedelta(days=self.rng.randint(5, 80))
                status = CleanupEvent.Status.COMPLETED
            else:
                event_date = now + timedelta(days=self.rng.randint(3, 45))
                status = CleanupEvent.Status.SCHEDULED
            point = self._random_point()
            event = CleanupEvent.objects.create(
                title=self.rng.choice(EVENT_TITLES),
                description="Join us for a community cleanup — gloves and bags provided!",
                location=point,
                district=self.assign_district(point),
                organizer=self.rng.choice(users[:8]),
                event_date=event_date,
                status=status,
                max_attendees=self.rng.choice([None, 15, 20, 25, 30]),
            )
            for attendee in self.rng.sample(users, self.rng.randint(5, min(20, len(users)))):
                EventRSVP.objects.get_or_create(
                    event=event, user=attendee,
                    defaults={"name": attendee.get_full_name(), "email": attendee.email},
                )
            events.append(event)
        return events

    def _create_challenges(self):
        today = timezone.now().date()
        specs = [
            ("Summer Cleanup Sprint", CleanupEvent.Status.SCHEDULED, -20, 40, 500, Challenge.Status.ACTIVE),
            ("Back-to-School Blitz", None, 20, 60, 300, Challenge.Status.UPCOMING),
            ("Spring Roadside Challenge", None, -120, -60, 400, Challenge.Status.COMPLETED),
            ("Winter Warm-Up Cleanup", None, -200, -150, 250, Challenge.Status.COMPLETED),
        ]
        for name, _unused, start_off, end_off, goal, status in specs:
            Challenge.objects.create(
                name=name,
                slug=f"{DEMO_SLUG_PREFIX}{slugify(name)}",
                description=f"Community-wide challenge: help us reach {goal} bags collected!",
                start_date=today + timedelta(days=start_off),
                end_date=today + timedelta(days=end_off),
                bag_goal=goal,
                status=status,
            )

    def _create_feedback(self, users, count):
        for i in range(count):
            message, ftype = self.rng.choice(FEEDBACK_MESSAGES)
            entry = FeedbackEntry.objects.create(
                feedback_type=ftype,
                status=self.rng.choice([
                    FeedbackEntry.Status.OPEN,
                    FeedbackEntry.Status.ACKNOWLEDGED,
                    FeedbackEntry.Status.CLOSED,
                ]),
                message=message,
                page_url="/",
                created_by=self.rng.choice(users),
            )
            when = self._days_ago(50)
            FeedbackEntry.objects.filter(pk=entry.pk).update(created_at=when)

    # -------------------------------------------------------------- log helper

    def _log(self, activity_type, actor, summary, when, trash_site=None, route_cleanup=None, proof=None):
        entry = ActivityLog.objects.create(
            activity_type=activity_type,
            actor=actor,
            trash_site=trash_site,
            route_cleanup=route_cleanup,
            proof=proof,
            summary=summary[:255],
        )
        ActivityLog.objects.filter(pk=entry.pk).update(created_at=when)

    # ------------------------------------------------------------------ reset

    def _demo_exists(self):
        user_model = get_user_model()
        return user_model.objects.filter(username__startswith=DEMO_USER_PREFIX).exists()

    def _reset_demo_data(self):
        user_model = get_user_model()
        demo_users = list(user_model.objects.filter(username__startswith=DEMO_USER_PREFIX))
        # Challenges and teams are not FK'd to users; remove by demo slug prefix.
        Challenge.objects.filter(slug__startswith=DEMO_SLUG_PREFIX).delete()
        Team.objects.filter(slug__startswith=DEMO_SLUG_PREFIX).delete()
        # Deleting the users cascades Profiles, memberships, RSVPs, and (via
        # created_by CASCADE? no — SET_NULL) leaves content; remove content first.
        ActivityLog.objects.filter(actor__in=demo_users).delete()
        FeedbackEntry.objects.filter(created_by__in=demo_users).delete()
        CleanupEvent.objects.filter(organizer__in=demo_users).delete()
        CleanupProof.objects.filter(created_by__in=demo_users).delete()
        RouteCleanup.objects.filter(created_by__in=demo_users).delete()
        TrashSite.objects.filter(created_by__in=demo_users).delete()
        count = len(demo_users)
        for user in demo_users:
            user.delete()
        return count
