import math
import uuid

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ValidationError


def _haversine_meters(point_a, point_b):
    lng1, lat1 = point_a
    lng2, lat2 = point_b
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)
    d_lat = lat2 - lat1
    d_lng = math.radians(lng2 - lng1)
    sin_lat = math.sin(d_lat / 2)
    sin_lng = math.sin(d_lng / 2)
    a = sin_lat * sin_lat + math.cos(lat1) * math.cos(lat2) * sin_lng * sin_lng
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return 6_371_008.8 * c


def _line_length_meters(linestring):
    coords = list(linestring.coords)
    if len(coords) < 2:
        return 0.0
    distance = 0.0
    for idx in range(len(coords) - 1):
        distance += _haversine_meters(coords[idx], coords[idx + 1])
    return distance


class District(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    geometry = models.MultiPolygonField(geography=True, srid=4326, spatial_index=True)
    active = models.BooleanField(default=True, db_index=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Profile(models.Model):
    class Role(models.TextChoices):
        MEMBER = "MEMBER", "Member"
        COORDINATOR = "COORDINATOR", "Coordinator"
        ADMIN = "ADMIN", "Admin"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER, db_index=True)
    public_profile = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class TrashSite(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        CLEANED = "CLEANED", "Cleaned"
        INVALID = "INVALID", "Invalid"

    class Severity(models.TextChoices):
        LIGHT = "LIGHT", "Light"
        MEDIUM = "MEDIUM", "Medium"
        HEAVY = "HEAVY", "Heavy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    location = models.PointField(geography=True, srid=4326, spatial_index=True)
    area = models.PolygonField(geography=True, srid=4326, spatial_index=True, null=True, blank=True)
    district = models.ForeignKey(
        District, on_delete=models.SET_NULL, null=True, blank=True, related_name="trash_sites"
    )
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices, blank=True)
    hazard_flag = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="trash_sites_created")
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="trash_sites_claimed"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="verifications"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cleaned_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_note = models.CharField(max_length=500, blank=True)
    work_order = models.CharField(max_length=100, blank=True)
    team = models.ForeignKey("Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="trash_sites")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.status} - {self.title or self.id}"


class RouteCleanup(models.Model):
    class Status(models.TextChoices):
        LOGGED = "LOGGED", "Logged"
        VERIFIED = "VERIFIED", "Verified"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    geometry = models.LineStringField(geography=True, srid=4326, spatial_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.LOGGED)
    notes = models.TextField(blank=True)
    distance_miles = models.FloatField(default=0.0)
    time_spent_minutes = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="routes_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.geometry:
            meters = _line_length_meters(self.geometry)
            self.distance_miles = meters * 0.000621371
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Route {self.id} ({self.distance_miles:.2f} mi)"


class CleanupProof(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trash_site = models.ForeignKey("TrashSite", on_delete=models.CASCADE, null=True, blank=True, related_name="proofs")
    route_cleanup = models.ForeignKey("RouteCleanup", on_delete=models.CASCADE, null=True, blank=True, related_name="proofs")
    note = models.TextField(blank=True)
    bags_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="proofs_created")
    team = models.ForeignKey("Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="cleanup_proofs")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if not self.trash_site and not self.route_cleanup:
            raise ValidationError("CleanupProof must reference either trash_site or route_cleanup.")

    def __str__(self):
        target = self.trash_site_id or self.route_cleanup_id
        return f"Proof {self.id} for {target}"


class Photo(models.Model):
    class PhotoType(models.TextChoices):
        REPORT = "REPORT", "Report"
        BEFORE = "BEFORE", "Before"
        AFTER = "AFTER", "After"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ImageField(upload_to="proof_photos/%Y/%m/%d")
    proof = models.ForeignKey(CleanupProof, on_delete=models.CASCADE, related_name="photos")
    photo_type = models.CharField(max_length=10, choices=PhotoType.choices, default=PhotoType.REPORT, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Photo {self.id}"


class ActivityLog(models.Model):
    class ActivityType(models.TextChoices):
        TRASH_REPORTED = "TRASH_REPORTED", "Trash Reported"
        TRASH_UPDATED = "TRASH_UPDATED", "Trash Updated"
        TRASH_CLEANED = "TRASH_CLEANED", "Trash Cleaned"
        ROUTE_LOGGED = "ROUTE_LOGGED", "Route Logged"
        PROOF_ADDED = "PROOF_ADDED", "Proof Added"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_logs")
    trash_site = models.ForeignKey(TrashSite, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_logs")
    route_cleanup = models.ForeignKey(
        RouteCleanup, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_logs"
    )
    proof = models.ForeignKey(CleanupProof, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_logs")
    summary = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.activity_type} by {self.actor or 'deleted user'}"


class FeedbackEntry(models.Model):
    class FeedbackType(models.TextChoices):
        BUG = "BUG", "Bug"
        REQUEST = "REQUEST", "Request"
        GENERAL = "GENERAL", "General"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        CLOSED = "CLOSED", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feedback_type = models.CharField(max_length=20, choices=FeedbackType.choices, default=FeedbackType.GENERAL, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    message = models.TextField()
    page_url = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="feedback_entries")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.feedback_type} from {self.created_by or 'deleted user'}"


class CleanupEvent(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    location = models.PointField(geography=True, srid=4326)
    district = models.ForeignKey(
        District, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    trash_site = models.ForeignKey(
        "TrashSite", on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="organized_events"
    )
    event_date = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    max_attendees = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_date"]

    def __str__(self):
        return f"{self.title} ({self.event_date.date()})"


class EventRSVP(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(CleanupEvent, on_delete=models.CASCADE, related_name="rsvps")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="event_rsvps"
    )
    name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    rsvp_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rsvp_at"]
        unique_together = [["event", "user"]]

    def __str__(self):
        return f"RSVP {self.id} for event {self.event_id}"


class Team(models.Model):
    class OrgType(models.TextChoices):
        SCHOOL = "SCHOOL", "School"
        CIVIC = "CIVIC", "Civic Group"
        CHURCH = "CHURCH", "Church"
        SCOUT = "SCOUT", "Scout Troop"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    org_type = models.CharField(max_length=20, choices=OrgType.choices, default=OrgType.OTHER)
    leader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="led_teams")
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True, related_name="teams")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    class Role(models.TextChoices):
        LEADER = "LEADER", "Leader"
        MEMBER = "MEMBER", "Member"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_memberships")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at"]
        unique_together = [["user", "team"]]

    def __str__(self):
        return f"{self.user.username} in {self.team.name}"


class PushSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="push_subscriptions")
    endpoint = models.TextField()
    p256dh = models.TextField()
    auth_key = models.TextField()
    saved_location = models.PointField(geography=True, srid=4326, null=True, blank=True)
    notification_radius_miles = models.FloatField(default=2.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PushSub {self.id}"


class IPBan(models.Model):
    ip_address = models.GenericIPAddressField(unique=True, db_index=True)
    reason = models.CharField(max_length=255, blank=True)
    banned_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ip_bans_created"
    )

    class Meta:
        ordering = ["-banned_at"]

    def __str__(self):
        return f"Ban {self.ip_address}"


class UserMapPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="map_preference",
    )
    default_county = models.CharField(max_length=100, blank=True)
    visible_district_slugs = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Map prefs for {self.user.username}"
