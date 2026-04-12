import json
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .middleware import IPBanMiddleware
from .models import (
    ActivityLog,
    Badge,
    Challenge,
    CleanupEvent,
    CleanupProof,
    District,
    EventRSVP,
    FeedbackEntry,
    IPBan,
    Photo,
    Profile,
    ScheduledJobLog,
    Team,
    TeamMembership,
    TrashSite,
    UserBadge,
    UserMapPreference,
)
from .services import assign_district
from .validators import validate_photo_uploads

User = get_user_model()

# Putnam County area (approximate) for test district geometry.
TEST_DISTRICT_POLY = Polygon(
    (
        (-85.60, 36.10),
        (-85.40, 36.10),
        (-85.40, 36.25),
        (-85.60, 36.25),
        (-85.60, 36.10),
    ),
    srid=4326,
)
TEST_DISTRICT_GEOM = MultiPolygon(TEST_DISTRICT_POLY, srid=4326)


def _tiny_image(name="test.jpg", content_type="image/jpeg"):
    """Return a minimal valid JPEG file for upload tests."""
    # Smallest valid JPEG: SOI + APP0 marker + EOI
    data = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9"
    )
    return SimpleUploadedFile(name, data, content_type=content_type)


# ---------------------------------------------------------------------------
# Disable rate limits for all tests except the dedicated RateLimitTests class
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class PublicAccessTests(TestCase):
    """Public endpoints must be accessible without login."""

    def test_map_view_is_public(self):
        response = self.client.get(reverse("map"))
        self.assertEqual(response.status_code, 200)

    def test_cleanups_view_is_public(self):
        response = self.client.get(reverse("cleanups"))
        self.assertEqual(response.status_code, 200)

    def test_healthz_is_public(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_features_api_is_public(self):
        response = self.client.get(reverse("api_features"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertIn("features", payload)

    def test_districts_api_is_public(self):
        response = self.client.get(reverse("api_districts"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("districts", response.json())

    def test_cleanups_list_api_is_public(self):
        response = self.client.get(reverse("api_cleanups_list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())


@override_settings(RATELIMIT_ENABLE=False)
class AuthGateTests(TestCase):
    """Write endpoints require authentication."""

    def test_trash_site_create_requires_login(self):
        response = self.client.post(
            reverse("api_trash_site_create"),
            {"lat": "36.16", "lng": "-85.50", "title": "test"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_mark_cleaned_requires_login(self):
        user = User.objects.create_user(username="temp", password="pass12345")
        site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326), created_by=user
        )
        response = self.client.post(
            reverse("api_trash_site_mark_cleaned", kwargs={"site_id": site.id})
        )
        self.assertEqual(response.status_code, 302)

    def test_feedback_requires_login(self):
        response = self.client.post(
            reverse("api_feedback_create"),
            {"message": "test", "feedback_type": "GENERAL"},
        )
        self.assertEqual(response.status_code, 302)

    def test_trash_site_update_requires_login(self):
        user = User.objects.create_user(username="temp2", password="pass12345")
        site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326), created_by=user
        )
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": site.id}),
            data=json.dumps({"title": "hack"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)


# ---------------------------------------------------------------------------
# District tests
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class DistrictModelTests(TestCase):
    def test_create_district_with_geometry(self):
        district = District.objects.create(
            name="Test District",
            slug="test-district",
            geometry=TEST_DISTRICT_GEOM,
        )
        self.assertTrue(district.active)
        self.assertEqual(str(district), "Test District")

    def test_assign_district_returns_matching_district(self):
        district = District.objects.create(
            name="District 3",
            slug="district-3",
            geometry=TEST_DISTRICT_GEOM,
        )
        inside_point = Point(-85.50, 36.16, srid=4326)
        result = assign_district(inside_point)
        self.assertEqual(result, district)

    def test_assign_district_returns_none_for_outside_point(self):
        District.objects.create(
            name="District 3",
            slug="district-3",
            geometry=TEST_DISTRICT_GEOM,
        )
        outside_point = Point(-80.00, 30.00, srid=4326)
        result = assign_district(outside_point)
        self.assertIsNone(result)

    def test_inactive_district_not_assigned(self):
        District.objects.create(
            name="Inactive District",
            slug="inactive",
            geometry=TEST_DISTRICT_GEOM,
            active=False,
        )
        inside_point = Point(-85.50, 36.16, srid=4326)
        result = assign_district(inside_point)
        self.assertIsNone(result)


@override_settings(RATELIMIT_ENABLE=False)
class DistrictApiTests(TestCase):
    def test_districts_api_returns_active_districts(self):
        District.objects.create(
            name="Active District",
            slug="active",
            geometry=TEST_DISTRICT_GEOM,
            active=True,
        )
        District.objects.create(
            name="Inactive District",
            slug="inactive",
            geometry=TEST_DISTRICT_GEOM,
            active=False,
        )
        response = self.client.get(reverse("api_districts"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["districts"]), 1)
        self.assertEqual(data["districts"][0]["slug"], "active")
        self.assertIn("geometry", data["districts"][0])

    def test_districts_api_geometry_is_geojson(self):
        District.objects.create(
            name="District 3",
            slug="district-3",
            geometry=TEST_DISTRICT_GEOM,
        )
        response = self.client.get(reverse("api_districts"))
        geom = response.json()["districts"][0]["geometry"]
        self.assertIn("type", geom)
        self.assertIn("coordinates", geom)


# ---------------------------------------------------------------------------
# Trash site lifecycle
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class TrashSiteApiLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="trash-user", password="pass12345")
        self.client.force_login(self.user)

    def test_create_trash_site_with_lat_lng(self):
        response = self.client.post(
            reverse("api_trash_site_create"),
            {
                "lat": "36.1627",
                "lng": "-85.5016",
                "title": "Roadside litter",
                "description": "Near greenway entrance",
                "severity": "MEDIUM",
                "hazard_flag": "true",
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIn("id", payload)
        self.assertEqual(payload["status"], TrashSite.Status.PENDING)
        self.assertEqual(payload["coordinates"], [-85.5016, 36.1627])
        self.assertEqual(payload["severity"], TrashSite.Severity.MEDIUM)
        self.assertTrue(payload["hazard_flag"])

        site = TrashSite.objects.get(id=payload["id"])
        self.assertEqual(site.location.srid, 4326)
        self.assertAlmostEqual(site.location.x, -85.5016, places=4)
        self.assertAlmostEqual(site.location.y, 36.1627, places=4)

    def test_create_trash_site_with_geojson_point(self):
        geojson = json.dumps({"type": "Point", "coordinates": [-85.50, 36.16]})
        response = self.client.post(
            reverse("api_trash_site_create"),
            {"geojson": geojson, "title": "Point GeoJSON"},
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["coordinates"], [-85.50, 36.16])
        self.assertIsNone(payload["area"])

    def test_create_trash_site_auto_assigns_district(self):
        district = District.objects.create(
            name="District 3",
            slug="district-3",
            geometry=TEST_DISTRICT_GEOM,
        )
        response = self.client.post(
            reverse("api_trash_site_create"),
            {"lat": "36.16", "lng": "-85.50", "title": "In district"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["district"], "district-3")

    def test_patch_trash_site_updates_fields(self):
        site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.PENDING,
            title="Original",
            created_by=self.user,
        )
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": site.id}),
            data=json.dumps({
                "status": TrashSite.Status.CLEANED,
                "title": "Updated",
                "severity": TrashSite.Severity.HEAVY,
                "hazard_flag": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], TrashSite.Status.CLEANED)
        self.assertEqual(payload["title"], "Updated")
        self.assertIsNotNone(payload["cleaned_at"])

    def test_cleaned_at_clears_on_status_revert(self):
        site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )
        self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": site.id}),
            data=json.dumps({"status": TrashSite.Status.CLEANED}),
            content_type="application/json",
        )
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": site.id}),
            data=json.dumps({"status": TrashSite.Status.PENDING}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["cleaned_at"])

    def test_detail_api_returns_site_info(self):
        site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            title="Detail test",
            created_by=self.user,
        )
        response = self.client.get(
            reverse("api_trash_site_detail", kwargs={"site_id": site.id})
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], str(site.id))
        self.assertIn("photos", payload)
        self.assertIn("report", payload["photos"])

    def test_detail_api_is_public(self):
        site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            title="Public detail",
            created_by=self.user,
        )
        self.client.logout()
        response = self.client.get(
            reverse("api_trash_site_detail", kwargs={"site_id": site.id})
        )
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Polygon area reports
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class TrashSitePolygonTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="poly-user", password="pass12345")
        self.client.force_login(self.user)

    def test_create_with_polygon_geojson(self):
        polygon_geojson = json.dumps({
            "type": "Polygon",
            "coordinates": [[
                [-85.505, 36.160],
                [-85.495, 36.160],
                [-85.495, 36.165],
                [-85.505, 36.165],
                [-85.505, 36.160],
            ]],
        })
        response = self.client.post(
            reverse("api_trash_site_create"),
            {"geojson": polygon_geojson, "title": "Area report"},
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIsNotNone(payload["area"])
        # Centroid should be set as the location
        self.assertAlmostEqual(payload["coordinates"][0], -85.50, delta=0.01)
        self.assertAlmostEqual(payload["coordinates"][1], 36.1625, delta=0.01)

    def test_feature_api_includes_area_flag(self):
        poly = Polygon(
            ((-85.505, 36.160), (-85.495, 36.160), (-85.495, 36.165),
             (-85.505, 36.165), (-85.505, 36.160)),
            srid=4326,
        )
        TrashSite.objects.create(
            location=poly.centroid,
            area=poly,
            title="Area site",
            created_by=self.user,
        )
        response = self.client.get(
            reverse("api_features"),
            {"bbox": "-85.51,36.15,-85.49,36.17"},
        )
        features = response.json()["features"]
        self.assertTrue(len(features) > 0)
        props = features[0]["properties"]
        self.assertTrue(props["has_area"])
        self.assertIn("area_geojson", props)


# ---------------------------------------------------------------------------
# Mark cleaned + before/after photos
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class MarkCleanedApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cleanup-user", password="pass12345")
        self.client.force_login(self.user)
        self.site = TrashSite.objects.create(
            location=Point(-85.5016, 36.1627, srid=4326),
            description="Trash near trail",
            created_by=self.user,
        )

    def test_mark_cleaned_sets_status_and_cleaned_at(self):
        response = self.client.post(
            reverse("api_trash_site_mark_cleaned", kwargs={"site_id": self.site.id}),
            {"note": "Removed litter", "bags_count": 2},
        )
        self.assertEqual(response.status_code, 200)
        self.site.refresh_from_db()
        self.assertEqual(self.site.status, TrashSite.Status.CLEANED)
        self.assertIsNotNone(self.site.cleaned_at)
        proof = CleanupProof.objects.get(trash_site=self.site)
        self.assertEqual(proof.bags_count, 2)

    def test_before_and_after_photos_get_correct_type(self):
        before_img = _tiny_image("before.jpg")
        after_img = _tiny_image("after.jpg")
        response = self.client.post(
            reverse("api_trash_site_mark_cleaned", kwargs={"site_id": self.site.id}),
            {
                "note": "Cleaned up",
                "bags_count": 1,
                "before_photos": before_img,
                "after_photos": after_img,
            },
        )
        self.assertEqual(response.status_code, 200)
        proof = CleanupProof.objects.get(trash_site=self.site)
        before_photos = proof.photos.filter(photo_type=Photo.PhotoType.BEFORE)
        after_photos = proof.photos.filter(photo_type=Photo.PhotoType.AFTER)
        self.assertEqual(before_photos.count(), 1)
        self.assertEqual(after_photos.count(), 1)

    def test_invalid_site_cannot_be_marked_cleaned(self):
        self.site.status = TrashSite.Status.INVALID
        self.site.save()
        response = self.client.post(
            reverse("api_trash_site_mark_cleaned", kwargs={"site_id": self.site.id}),
            {"note": "Attempt"},
        )
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Features filter API
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class FeaturesFilterApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="filter-user", password="pass12345")
        self.in_bbox_pending = TrashSite.objects.create(
            location=Point(-85.5020, 36.1630, srid=4326),
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )
        self.in_bbox_cleaned = TrashSite.objects.create(
            location=Point(-85.4995, 36.1620, srid=4326),
            status=TrashSite.Status.CLEANED,
            created_by=self.user,
        )
        self.in_bbox_old = TrashSite.objects.create(
            location=Point(-85.4980, 36.1610, srid=4326),
            status=TrashSite.Status.CLEANED,
            created_by=self.user,
        )
        TrashSite.objects.filter(id=self.in_bbox_old.id).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        self.out_of_bbox = TrashSite.objects.create(
            location=Point(-85.7000, 36.3000, srid=4326),
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )

    def _ids(self, payload):
        return {f["properties"]["id"] for f in payload["features"]}

    def test_bbox_filters_features(self):
        response = self.client.get(
            reverse("api_features"),
            {"bbox": "-85.51,36.15,-85.49,36.17", "days": "all"},
        )
        self.assertEqual(response.status_code, 200)
        ids = self._ids(response.json())
        self.assertIn(str(self.in_bbox_pending.id), ids)
        self.assertNotIn(str(self.out_of_bbox.id), ids)

    def test_status_filter(self):
        response = self.client.get(
            reverse("api_features"),
            {"bbox": "-85.51,36.15,-85.49,36.17", "status": "CLEANED", "days": "all"},
        )
        ids = self._ids(response.json())
        self.assertNotIn(str(self.in_bbox_pending.id), ids)
        self.assertIn(str(self.in_bbox_cleaned.id), ids)

    def test_days_filter(self):
        response = self.client.get(
            reverse("api_features"),
            {"bbox": "-85.51,36.15,-85.49,36.17", "status": "CLEANED", "days": "7"},
        )
        ids = self._ids(response.json())
        self.assertIn(str(self.in_bbox_cleaned.id), ids)
        self.assertNotIn(str(self.in_bbox_old.id), ids)

    def test_district_filter(self):
        district = District.objects.create(
            name="D3", slug="district-3", geometry=TEST_DISTRICT_GEOM
        )
        self.in_bbox_pending.district = district
        self.in_bbox_pending.save()
        response = self.client.get(
            reverse("api_features"),
            {"district": "district-3", "days": "all"},
        )
        ids = self._ids(response.json())
        self.assertIn(str(self.in_bbox_pending.id), ids)
        self.assertNotIn(str(self.in_bbox_cleaned.id), ids)

    def test_no_route_features(self):
        """Features API should only return trash_site types, not routes."""
        response = self.client.get(reverse("api_features"))
        for feature in response.json()["features"]:
            self.assertEqual(feature["properties"]["type"], "trash_site")


# ---------------------------------------------------------------------------
# Cleanups page and API
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class CleanupsPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cleanups-user", password="pass12345")

    def test_cleanups_page_renders(self):
        response = self.client.get(reverse("cleanups"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cleanup")

    def test_cleanups_list_api_returns_only_cleaned(self):
        TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )
        cleaned = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.CLEANED,
            cleaned_at=timezone.now(),
            created_by=self.user,
        )
        response = self.client.get(reverse("api_cleanups_list"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}
        self.assertIn(str(cleaned.id), result_ids)
        self.assertEqual(len(result_ids), 1)

    def test_cleanups_list_api_pagination(self):
        for i in range(5):
            TrashSite.objects.create(
                location=Point(-85.50, 36.16, srid=4326),
                status=TrashSite.Status.CLEANED,
                cleaned_at=timezone.now(),
                created_by=self.user,
            )
        response = self.client.get(
            reverse("api_cleanups_list"), {"page_size": 2, "page": 1}
        )
        data = response.json()
        self.assertEqual(data["count"], 5)
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["num_pages"], 3)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class ApiValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="val-user", password="pass12345")
        self.client.force_login(self.user)
        self.site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326), created_by=self.user
        )

    def test_invalid_status_patch_returns_error(self):
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": self.site.id}),
            data=json.dumps({"status": "NOT_A_REAL_STATUS"}),
            content_type="application/json",
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_invalid_severity_on_create_returns_error(self):
        response = self.client.post(
            reverse("api_trash_site_create"),
            {"lat": "36.16", "lng": "-85.50", "severity": "EXTREME"},
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_missing_coordinates_returns_error(self):
        response = self.client.post(
            reverse("api_trash_site_create"), {"title": "No coords"}
        )
        self.assertGreaterEqual(response.status_code, 400)

    def test_invalid_geojson_type_returns_error(self):
        geojson = json.dumps({"type": "LineString", "coordinates": [[-85.5, 36.16], [-85.49, 36.16]]})
        response = self.client.post(
            reverse("api_trash_site_create"),
            {"geojson": geojson, "title": "Bad type"},
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())


# ---------------------------------------------------------------------------
# Photo upload validation
# ---------------------------------------------------------------------------
class PhotoUploadValidationTests(TestCase):
    def test_max_count_exceeded(self):
        files = [_tiny_image(f"img{i}.jpg") for i in range(6)]
        with self.assertRaises(ValidationError):
            validate_photo_uploads(files)

    def test_max_size_exceeded(self):
        big_file = SimpleUploadedFile(
            "big.jpg",
            b"\xff\xd8" + b"\x00" * (11 * 1024 * 1024),
            content_type="image/jpeg",
        )
        with self.assertRaises(ValidationError):
            validate_photo_uploads([big_file])

    def test_invalid_mime_type(self):
        bad_file = SimpleUploadedFile("doc.pdf", b"%PDF-1.4", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_photo_uploads([bad_file])

    def test_valid_files_pass(self):
        files = [_tiny_image(f"ok{i}.jpg") for i in range(5)]
        validate_photo_uploads(files)  # Should not raise


# ---------------------------------------------------------------------------
# Permission / role tests
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class PermissionRoleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pass12345")
        self.other = User.objects.create_user(username="other", password="pass12345")
        self.admin = User.objects.create_user(username="admin", password="pass12345")
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save(update_fields=["role"])
        self.site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            title="Owner site",
            created_by=self.owner,
        )

    def test_non_owner_cannot_patch(self):
        self.client.force_login(self.other)
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": self.site.id}),
            data=json.dumps({"title": "Nope"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_non_admin_cannot_invalidate(self):
        self.client.force_login(self.owner)
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": self.site.id}),
            data=json.dumps({"status": TrashSite.Status.INVALID}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_invalidate(self):
        self.client.force_login(self.admin)
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": self.site.id}),
            data=json.dumps({"status": TrashSite.Status.INVALID}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.site.refresh_from_db()
        self.assertEqual(self.site.status, TrashSite.Status.INVALID)


# ---------------------------------------------------------------------------
# IP ban middleware
# ---------------------------------------------------------------------------
class IPBanMiddlewareTests(TestCase):
    def test_banned_ip_returns_403(self):
        IPBan.objects.create(ip_address="1.2.3.4", reason="Spam")
        response = self.client.get(
            reverse("healthz"), REMOTE_ADDR="1.2.3.4"
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("error", response.json())

    def test_expired_ban_passes(self):
        IPBan.objects.create(
            ip_address="1.2.3.5",
            reason="Expired",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        response = self.client.get(
            reverse("healthz"), REMOTE_ADDR="1.2.3.5"
        )
        self.assertEqual(response.status_code, 200)

    def test_future_expiry_still_banned(self):
        IPBan.objects.create(
            ip_address="1.2.3.6",
            reason="Active",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        response = self.client.get(
            reverse("healthz"), REMOTE_ADDR="1.2.3.6"
        )
        self.assertEqual(response.status_code, 403)

    def test_clean_ip_passes(self):
        response = self.client.get(
            reverse("healthz"), REMOTE_ADDR="9.9.9.9"
        )
        self.assertEqual(response.status_code, 200)

    def test_xff_header_used(self):
        IPBan.objects.create(ip_address="10.0.0.1", reason="XFF test")
        response = self.client.get(
            reverse("healthz"),
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="10.0.0.1, 192.168.1.1",
        )
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class FeedbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="fb-user", password="pass12345")

    def test_feedback_submission_creates_entry(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_feedback_create"),
            {
                "feedback_type": FeedbackEntry.FeedbackType.BUG,
                "message": "Map did not recenter.",
                "page_url": "/",
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["feedback_type"], FeedbackEntry.FeedbackType.BUG)
        self.assertEqual(FeedbackEntry.objects.count(), 1)

    def test_feedback_missing_message_returns_error(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_feedback_create"),
            {"feedback_type": "GENERAL", "message": ""},
        )
        self.assertGreaterEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class SignupTests(TestCase):
    def test_signup_page_renders(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)

    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "newuser",
                "password1": "Str0ngP@ss!",
                "password2": "Str0ngP@ss!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_authenticated_user_redirected_from_signup(self):
        user = User.objects.create_user(username="existing", password="pass12345")
        self.client.force_login(user)
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")


# ---------------------------------------------------------------------------
# API surface contract
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class ApiSurfaceContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="contract-user", password="pass12345")
        self.client.force_login(self.user)
        self.site = TrashSite.objects.create(
            location=Point(-85.5016, 36.1627, srid=4326),
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )

    def test_features_api_shape(self):
        response = self.client.get(reverse("api_features"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertIn("features", payload)
        if payload["features"]:
            feature = payload["features"][0]
            self.assertIn("geometry", feature)
            self.assertIn("properties", feature)
            props = feature["properties"]
            for key in ("id", "type", "status", "severity", "has_area"):
                self.assertIn(key, props)

    def test_detail_api_shape(self):
        response = self.client.get(
            reverse("api_trash_site_detail", kwargs={"site_id": self.site.id})
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in ("id", "status", "coordinates", "photos", "proofs", "permissions", "district"):
            self.assertIn(key, payload)
        self.assertIn("report", payload["photos"])
        self.assertIn("before", payload["photos"])
        self.assertIn("after", payload["photos"])

    def test_cleanups_list_api_shape(self):
        response = self.client.get(reverse("api_cleanups_list"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in ("count", "page", "num_pages", "results"):
            self.assertIn(key, payload)

    def test_districts_api_shape(self):
        District.objects.create(
            name="D3", slug="d3", geometry=TEST_DISTRICT_GEOM
        )
        response = self.client.get(reverse("api_districts"))
        payload = response.json()
        self.assertIn("districts", payload)
        d = payload["districts"][0]
        for key in ("id", "name", "slug", "geometry"):
            self.assertIn(key, d)

    def test_removed_endpoints_return_404(self):
        """Verify removed route/activity endpoints no longer resolve."""
        for name in ("api_route_cleanup_create", "api_route_cleanup_detail_root", "api_activity"):
            with self.assertRaises(Exception):
                reverse(name)


# ---------------------------------------------------------------------------
# Activity logging (integration)
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class ActivityLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="activity-user", password="pass12345")
        self.client.force_login(self.user)

    def test_report_and_cleanup_create_activity_logs(self):
        response = self.client.post(
            reverse("api_trash_site_create"),
            {"lat": "36.16", "lng": "-85.50", "title": "Test"},
        )
        self.assertEqual(response.status_code, 201)
        site_id = response.json()["id"]

        self.client.post(
            reverse("api_trash_site_mark_cleaned", kwargs={"site_id": site_id}),
            {"note": "Done", "bags_count": 1},
        )

        types = set(
            ActivityLog.objects.values_list("activity_type", flat=True)
        )
        self.assertIn(ActivityLog.ActivityType.TRASH_REPORTED, types)
        self.assertIn(ActivityLog.ActivityType.TRASH_CLEANED, types)


# ---------------------------------------------------------------------------
# Phase 1A — Impact counter
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class ImpactApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="impact-user", password="pass12345")

    def test_impact_api_is_public(self):
        response = self.client.get(reverse("api_impact"))
        self.assertEqual(response.status_code, 200)

    def test_impact_api_shape(self):
        response = self.client.get(reverse("api_impact"))
        data = response.json()
        for key in ("bags_collected", "sites_cleaned", "sites_reported", "active_volunteers_this_month"):
            self.assertIn(key, data)

    def test_impact_api_counts_are_accurate(self):
        # One pending site
        site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )
        # One cleaned site with 5 bags
        cleaned = TrashSite.objects.create(
            location=Point(-85.51, 36.17, srid=4326),
            status=TrashSite.Status.CLEANED,
            created_by=self.user,
        )
        CleanupProof.objects.create(
            trash_site=cleaned,
            bags_count=5,
            created_by=self.user,
        )
        # Bust the 5-minute cache so we get fresh counts
        from django.core.cache import cache
        cache.delete("impact_stats")

        response = self.client.get(reverse("api_impact"))
        data = response.json()
        self.assertEqual(data["sites_reported"], 2)
        self.assertEqual(data["sites_cleaned"], 1)
        self.assertEqual(data["bags_collected"], 5)


# ---------------------------------------------------------------------------
# Phase 1B — Heatmap
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class HeatmapApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="heat-user", password="pass12345")

    def test_heatmap_api_is_public(self):
        response = self.client.get(reverse("api_heatmap"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("points", response.json())

    def test_heatmap_excludes_cleaned_sites(self):
        TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.PENDING,
            severity=TrashSite.Severity.HEAVY,
            created_by=self.user,
        )
        TrashSite.objects.create(
            location=Point(-85.51, 36.17, srid=4326),
            status=TrashSite.Status.CLEANED,
            severity=TrashSite.Severity.HEAVY,
            created_by=self.user,
        )
        response = self.client.get(reverse("api_heatmap"))
        points = response.json()["points"]
        self.assertEqual(len(points), 1)

    def test_heatmap_intensity_by_severity(self):
        for sev, expected_intensity in [("LIGHT", 0.3), ("MEDIUM", 0.6), ("HEAVY", 1.0)]:
            TrashSite.objects.create(
                location=Point(-85.50, 36.16, srid=4326),
                status=TrashSite.Status.PENDING,
                severity=sev,
                created_by=self.user,
            )
        from django.core.cache import cache
        cache.clear()
        response = self.client.get(reverse("api_heatmap"))
        points = response.json()["points"]
        intensities = {p[2] for p in points}
        self.assertIn(0.3, intensities)
        self.assertIn(0.6, intensities)
        self.assertIn(1.0, intensities)


# ---------------------------------------------------------------------------
# Phase 1C — Share view
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class ShareViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="share-user", password="pass12345")
        self.site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            title="Litter on Route 70",
            status=TrashSite.Status.CLEANED,
            created_by=self.user,
        )

    def test_share_view_is_public(self):
        response = self.client.get(reverse("share_site", kwargs={"site_id": self.site.id}))
        self.assertEqual(response.status_code, 200)

    def test_share_view_404_for_nonexistent_site(self):
        import uuid
        response = self.client.get(reverse("share_site", kwargs={"site_id": uuid.uuid4()}))
        self.assertEqual(response.status_code, 404)

    def test_share_view_contains_og_title(self):
        response = self.client.get(reverse("share_site", kwargs={"site_id": self.site.id}))
        self.assertContains(response, "og:title")


# ---------------------------------------------------------------------------
# Phase 2C — Leaderboard
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class LeaderboardViewTests(TestCase):
    def test_leaderboard_page_is_public(self):
        response = self.client.get(reverse("leaderboard"))
        self.assertEqual(response.status_code, 200)


@override_settings(RATELIMIT_ENABLE=False)
class LeaderboardApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="lb-user", password="pass12345")

    def test_leaderboard_api_is_public(self):
        response = self.client.get(reverse("api_leaderboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_leaderboard_api_period_alltime(self):
        response = self.client.get(reverse("api_leaderboard"), {"period": "alltime"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_leaderboard_masks_private_users(self):
        # User with public_profile=False (default) submits a cleanup
        site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.CLEANED,
            created_by=self.user,
        )
        CleanupProof.objects.create(trash_site=site, bags_count=1, created_by=self.user)
        # Ensure profile is private
        self.user.profile.public_profile = False
        self.user.profile.save()

        response = self.client.get(reverse("api_leaderboard"), {"period": "alltime"})
        data = response.json()
        if data["results"]:
            self.assertEqual(data["results"][0]["username"], "Anonymous")

    def test_leaderboard_shows_public_users(self):
        self.user.profile.public_profile = True
        self.user.profile.save()
        site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.CLEANED,
            created_by=self.user,
        )
        CleanupProof.objects.create(trash_site=site, bags_count=1, created_by=self.user)

        response = self.client.get(reverse("api_leaderboard"), {"period": "alltime"})
        data = response.json()
        usernames = [r["username"] for r in data["results"]]
        self.assertIn(self.user.username, usernames)


# ---------------------------------------------------------------------------
# Phase 2A — Verify cleanup
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class VerifyApiTests(TestCase):
    def setUp(self):
        self.regular = User.objects.create_user(username="regular", password="pass12345")
        self.coordinator = User.objects.create_user(username="coord", password="pass12345")
        self.coordinator.profile.role = Profile.Role.COORDINATOR
        self.coordinator.profile.save()
        self.admin_user = User.objects.create_user(username="adm", password="pass12345")
        self.admin_user.profile.role = Profile.Role.ADMIN
        self.admin_user.profile.save()
        self.site = TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.CLEANED,
            created_by=self.regular,
        )

    def test_regular_user_cannot_verify(self):
        self.client.force_login(self.regular)
        response = self.client.post(
            reverse("api_trash_site_verify", kwargs={"site_id": self.site.id}),
            data=json.dumps({"verification_note": "looks clean"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_coordinator_can_verify(self):
        self.client.force_login(self.coordinator)
        response = self.client.post(
            reverse("api_trash_site_verify", kwargs={"site_id": self.site.id}),
            data=json.dumps({"verification_note": "Confirmed", "work_order": "WO-001"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.site.refresh_from_db()
        self.assertIsNotNone(self.site.verified_at)
        self.assertEqual(self.site.work_order, "WO-001")

    def test_admin_can_verify(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("api_trash_site_verify", kwargs={"site_id": self.site.id}),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_cannot_verify_pending_site(self):
        self.site.status = TrashSite.Status.PENDING
        self.site.save()
        self.client.force_login(self.coordinator)
        response = self.client.post(
            reverse("api_trash_site_verify", kwargs={"site_id": self.site.id}),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())


# ---------------------------------------------------------------------------
# Phase 3 — Cleanup events + RSVP
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class EventsViewTests(TestCase):
    def test_events_page_is_public(self):
        response = self.client.get(reverse("events"))
        self.assertEqual(response.status_code, 200)


@override_settings(RATELIMIT_ENABLE=False)
class EventsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="event-user", password="pass12345")
        self.other = User.objects.create_user(username="other-user", password="pass12345")
        self.admin_user = User.objects.create_user(username="event-admin", password="pass12345")
        self.admin_user.profile.role = Profile.Role.ADMIN
        self.admin_user.profile.save()
        self.future_date = (timezone.now() + timedelta(days=7)).isoformat()

    def test_list_events_is_public(self):
        response = self.client.get(reverse("api_events_list"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for key in ("count", "page", "num_pages", "results"):
            self.assertIn(key, data)

    def test_create_event_requires_auth(self):
        response = self.client.post(
            reverse("api_events_list"),
            data=json.dumps({"title": "Cleanup Day", "lat": "36.16", "lng": "-85.50", "event_date": self.future_date}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_create_event_authenticated(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_events_list"),
            data=json.dumps({
                "title": "Park Cleanup",
                "lat": "36.16",
                "lng": "-85.50",
                "event_date": self.future_date,
                "max_attendees": 20,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["title"], "Park Cleanup")
        self.assertEqual(data["max_attendees"], 20)
        self.assertEqual(data["organizer"], self.user.username)

    def test_event_detail_is_public(self):
        event = CleanupEvent.objects.create(
            title="Test Event",
            location=Point(-85.50, 36.16, srid=4326),
            event_date=timezone.now() + timedelta(days=3),
            organizer=self.user,
        )
        response = self.client.get(reverse("api_event_detail", kwargs={"event_id": event.id}))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for key in ("id", "title", "event_date", "status", "rsvp_count", "coordinates"):
            self.assertIn(key, data)

    def test_rsvp_requires_auth(self):
        event = CleanupEvent.objects.create(
            title="RSVP Test",
            location=Point(-85.50, 36.16, srid=4326),
            event_date=timezone.now() + timedelta(days=3),
            organizer=self.user,
        )
        response = self.client.post(
            reverse("api_event_rsvp", kwargs={"event_id": event.id}),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_rsvp_creates_record(self):
        event = CleanupEvent.objects.create(
            title="RSVP Test",
            location=Point(-85.50, 36.16, srid=4326),
            event_date=timezone.now() + timedelta(days=3),
            organizer=self.user,
        )
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("api_event_rsvp", kwargs={"event_id": event.id}),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EventRSVP.objects.filter(event=event).count(), 1)
        self.assertEqual(response.json()["rsvp_count"], 1)

    def test_duplicate_rsvp_returns_error(self):
        event = CleanupEvent.objects.create(
            title="Dupe RSVP",
            location=Point(-85.50, 36.16, srid=4326),
            event_date=timezone.now() + timedelta(days=3),
            organizer=self.user,
        )
        EventRSVP.objects.create(event=event, user=self.other)
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("api_event_rsvp", kwargs={"event_id": event.id}),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_cancel_rsvp(self):
        event = CleanupEvent.objects.create(
            title="Cancel RSVP",
            location=Point(-85.50, 36.16, srid=4326),
            event_date=timezone.now() + timedelta(days=3),
            organizer=self.user,
        )
        EventRSVP.objects.create(event=event, user=self.other)
        self.client.force_login(self.other)
        response = self.client.delete(
            reverse("api_event_rsvp", kwargs={"event_id": event.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EventRSVP.objects.filter(event=event).count(), 0)

    def test_max_attendees_enforced(self):
        event = CleanupEvent.objects.create(
            title="Full Event",
            location=Point(-85.50, 36.16, srid=4326),
            event_date=timezone.now() + timedelta(days=3),
            organizer=self.user,
            max_attendees=1,
        )
        EventRSVP.objects.create(event=event, user=self.user)
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("api_event_rsvp", kwargs={"event_id": event.id}),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_organizer_can_complete_event(self):
        event = CleanupEvent.objects.create(
            title="Complete Me",
            location=Point(-85.50, 36.16, srid=4326),
            event_date=timezone.now() + timedelta(days=3),
            organizer=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_event_complete", kwargs={"event_id": event.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], CleanupEvent.Status.COMPLETED)

    def test_non_organizer_cannot_complete_event(self):
        event = CleanupEvent.objects.create(
            title="Not Yours",
            location=Point(-85.50, 36.16, srid=4326),
            event_date=timezone.now() + timedelta(days=3),
            organizer=self.user,
        )
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("api_event_complete", kwargs={"event_id": event.id}),
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_complete_any_event(self):
        event = CleanupEvent.objects.create(
            title="Admin Complete",
            location=Point(-85.50, 36.16, srid=4326),
            event_date=timezone.now() + timedelta(days=3),
            organizer=self.user,
        )
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("api_event_complete", kwargs={"event_id": event.id}),
        )
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Phase 4A — Teams
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class TeamsViewTests(TestCase):
    def test_teams_page_is_public(self):
        response = self.client.get(reverse("teams"))
        self.assertEqual(response.status_code, 200)


@override_settings(RATELIMIT_ENABLE=False)
class TeamsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="team-user", password="pass12345")
        self.other = User.objects.create_user(username="team-other", password="pass12345")

    def test_list_teams_is_public(self):
        response = self.client.get(reverse("api_teams_list"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("results", data)

    def test_create_team_requires_auth(self):
        response = self.client.post(
            reverse("api_teams_list"),
            data=json.dumps({"name": "Scouts Troop 1"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_create_team_authenticated(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_teams_list"),
            data=json.dumps({"name": "Riverside Cleaners", "org_type": "CIVIC"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["name"], "Riverside Cleaners")
        self.assertEqual(data["org_type"], "CIVIC")
        self.assertEqual(data["leader"], self.user.username)
        self.assertEqual(data["member_count"], 1)  # creator is auto-added as leader

    def test_create_team_auto_adds_creator_as_leader(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("api_teams_list"),
            data=json.dumps({"name": "Auto Leader Team"}),
            content_type="application/json",
        )
        team = Team.objects.get(name="Auto Leader Team")
        membership = TeamMembership.objects.get(team=team, user=self.user)
        self.assertEqual(membership.role, TeamMembership.Role.LEADER)

    def test_duplicate_slug_returns_error(self):
        Team.objects.create(name="Existing Team", slug="existing-team")
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_teams_list"),
            data=json.dumps({"name": "Existing Team", "slug": "existing-team"}),
            content_type="application/json",
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_team_detail_is_public(self):
        team = Team.objects.create(name="Public Team", slug="public-team")
        response = self.client.get(reverse("api_team_detail", kwargs={"team_slug": "public-team"}))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for key in ("id", "name", "slug", "org_type", "member_count"):
            self.assertIn(key, data)

    def test_join_team_requires_auth(self):
        team = Team.objects.create(name="Auth Team", slug="auth-team")
        response = self.client.post(reverse("api_team_join", kwargs={"team_slug": "auth-team"}))
        self.assertEqual(response.status_code, 302)  # login redirect

    def test_join_team_creates_membership(self):
        team = Team.objects.create(name="Join Team", slug="join-team", leader=self.user)
        self.client.force_login(self.other)
        response = self.client.post(reverse("api_team_join", kwargs={"team_slug": "join-team"}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TeamMembership.objects.filter(team=team, user=self.other).exists())

    def test_duplicate_join_returns_error(self):
        team = Team.objects.create(name="No Dupe Team", slug="no-dupe-team")
        TeamMembership.objects.create(team=team, user=self.other)
        self.client.force_login(self.other)
        response = self.client.post(reverse("api_team_join", kwargs={"team_slug": "no-dupe-team"}))
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())


# ---------------------------------------------------------------------------
# Phase 5E — Badges
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class BadgesApiTests(TestCase):
    def test_badges_api_is_public(self):
        response = self.client.get(reverse("api_badges"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("badges", response.json())

    def test_badges_api_shows_earned_status_for_auth_user(self):
        user = User.objects.create_user(username="badge-user", password="pass12345")
        badge = Badge.objects.create(slug="first-cleanup", name="First Cleanup", description="Cleaned a site", icon="🧹")
        UserBadge.objects.create(user=user, badge=badge)

        self.client.force_login(user)
        response = self.client.get(reverse("api_badges"))
        data = response.json()
        earned = [b for b in data["badges"] if b["slug"] == "first-cleanup"]
        self.assertEqual(len(earned), 1)
        self.assertTrue(earned[0]["earned"])


# ---------------------------------------------------------------------------
# Phase 5F — Challenges
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class ChallengesViewTests(TestCase):
    def test_challenges_page_is_public(self):
        response = self.client.get(reverse("challenges"))
        self.assertEqual(response.status_code, 200)


@override_settings(RATELIMIT_ENABLE=False)
class ChallengesApiTests(TestCase):
    def setUp(self):
        self.challenge = Challenge.objects.create(
            name="Spring Clean",
            slug="spring-clean",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timedelta(days=30)).date(),
            bag_goal=100,
            status=Challenge.Status.ACTIVE,
        )

    def test_list_challenges_is_public(self):
        response = self.client.get(reverse("api_challenges_list"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)

    def test_challenge_detail_is_public(self):
        response = self.client.get(
            reverse("api_challenge_detail", kwargs={"challenge_slug": "spring-clean"})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for key in ("name", "slug", "bag_goal", "status"):
            self.assertIn(key, data)

    def test_challenge_detail_404_for_unknown_slug(self):
        response = self.client.get(
            reverse("api_challenge_detail", kwargs={"challenge_slug": "not-a-real-challenge"})
        )
        self.assertEqual(response.status_code, 404)

    def test_completed_challenges_excluded_from_list(self):
        Challenge.objects.create(
            name="Old Challenge",
            slug="old-challenge",
            start_date=(timezone.now() - timedelta(days=60)).date(),
            end_date=(timezone.now() - timedelta(days=30)).date(),
            bag_goal=50,
            status=Challenge.Status.COMPLETED,
        )
        response = self.client.get(reverse("api_challenges_list"))
        slugs = [r["slug"] for r in response.json()["results"]]
        self.assertIn("spring-clean", slugs)
        self.assertNotIn("old-challenge", slugs)


# ---------------------------------------------------------------------------
# Phase 5H — Embed map
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class EmbedMapTests(TestCase):
    def test_embed_is_public(self):
        response = self.client.get(reverse("embed_map"))
        self.assertEqual(response.status_code, 200)

    def test_embed_allows_iframes(self):
        response = self.client.get(reverse("embed_map"))
        # xframe_options_exempt means X-Frame-Options is NOT set to DENY/SAMEORIGIN
        self.assertNotEqual(response.get("X-Frame-Options", ""), "DENY")
        self.assertNotEqual(response.get("X-Frame-Options", ""), "SAMEORIGIN")


# ---------------------------------------------------------------------------
# Phase 5B — Cron health check
# ---------------------------------------------------------------------------
class HealthzCronTests(TestCase):
    def test_healthz_cron_is_public(self):
        response = self.client.get(reverse("healthz_cron"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("jobs", response.json())

    def test_healthz_cron_shows_job_status(self):
        ScheduledJobLog.objects.create(
            job_name="send_monthly_report",
            last_status="ok",
            last_run_at=timezone.now(),
        )
        response = self.client.get(reverse("healthz_cron"))
        jobs = response.json()["jobs"]
        self.assertIn("send_monthly_report", jobs)
        job = jobs["send_monthly_report"]
        for key in ("last_run_at", "last_success_at", "status"):
            self.assertIn(key, job)
        self.assertEqual(job["status"], "ok")


# ---------------------------------------------------------------------------
# Phase 6A — Coordinator dashboard
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class DashboardViewTests(TestCase):
    def setUp(self):
        self.regular = User.objects.create_user(username="dash-regular", password="pass12345")
        self.coordinator = User.objects.create_user(username="dash-coord", password="pass12345")
        self.coordinator.profile.role = Profile.Role.COORDINATOR
        self.coordinator.profile.save()
        self.admin_user = User.objects.create_user(username="dash-admin", password="pass12345")
        self.admin_user.profile.role = Profile.Role.ADMIN
        self.admin_user.profile.save()
        self.staff = User.objects.create_user(username="dash-staff", password="pass12345", is_staff=True)

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_regular_user_gets_403(self):
        self.client.force_login(self.regular)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_coordinator_sees_dashboard(self):
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_admin_sees_dashboard(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_staff_sees_dashboard(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Phase 6B — Data export
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class ExportApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="export-user", password="pass12345")
        self.coordinator = User.objects.create_user(username="export-coord", password="pass12345")
        self.coordinator.profile.role = Profile.Role.COORDINATOR
        self.coordinator.profile.save()
        TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            title="Export Site",
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )

    def test_export_requires_auth(self):
        response = self.client.get(reverse("api_export_sites", kwargs={"fmt": "csv"}))
        self.assertEqual(response.status_code, 302)

    def test_export_csv_returns_csv_content_type(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api_export_sites", kwargs={"fmt": "csv"}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

    def test_export_csv_has_header_row(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api_export_sites", kwargs={"fmt": "csv"}))
        content = response.content.decode("utf-8")
        first_line = content.splitlines()[0]
        self.assertIn("id", first_line)
        self.assertIn("status", first_line)

    def test_export_geojson_returns_geojson_content_type(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api_export_sites", kwargs={"fmt": "geojson"}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("geo+json", response["Content-Type"])

    def test_export_geojson_is_valid_feature_collection(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api_export_sites", kwargs={"fmt": "geojson"}))
        data = json.loads(response.content)
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertIn("features", data)

    def test_export_invalid_format_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api_export_sites", kwargs={"fmt": "xml"}))
        self.assertEqual(response.status_code, 404)

    def test_coordinator_can_export_all_statuses(self):
        self.client.force_login(self.coordinator)
        response = self.client.get(reverse("api_export_sites", kwargs={"fmt": "csv"}))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Phase 6C — District stats API
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class DistrictStatsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="stats-user", password="pass12345")
        self.district = District.objects.create(
            name="Test District",
            slug="test-district",
            geometry=TEST_DISTRICT_GEOM,
        )

    def test_district_stats_is_public(self):
        response = self.client.get(
            reverse("api_district_stats", kwargs={"district_slug": "test-district"})
        )
        self.assertEqual(response.status_code, 200)

    def test_district_stats_shape(self):
        response = self.client.get(
            reverse("api_district_stats", kwargs={"district_slug": "test-district"})
        )
        data = response.json()
        for key in ("slug", "name", "site_count", "cleaned_count", "pending_count",
                    "chronic_count", "bags_total", "top_volunteers", "recent_cleanups"):
            self.assertIn(key, data)

    def test_district_stats_counts_accurately(self):
        TrashSite.objects.create(
            location=Point(-85.50, 36.16, srid=4326),
            status=TrashSite.Status.PENDING,
            district=self.district,
            created_by=self.user,
        )
        cleaned = TrashSite.objects.create(
            location=Point(-85.51, 36.17, srid=4326),
            status=TrashSite.Status.CLEANED,
            district=self.district,
            created_by=self.user,
        )
        CleanupProof.objects.create(trash_site=cleaned, bags_count=3, created_by=self.user)

        response = self.client.get(
            reverse("api_district_stats", kwargs={"district_slug": "test-district"})
        )
        data = response.json()
        self.assertEqual(data["site_count"], 2)
        self.assertEqual(data["cleaned_count"], 1)
        self.assertEqual(data["pending_count"], 1)
        self.assertEqual(data["bags_total"], 3)

    def test_district_stats_404_for_inactive(self):
        District.objects.create(
            name="Inactive",
            slug="inactive-district",
            geometry=TEST_DISTRICT_GEOM,
            active=False,
        )
        response = self.client.get(
            reverse("api_district_stats", kwargs={"district_slug": "inactive-district"})
        )
        self.assertEqual(response.status_code, 404)

    def test_district_stats_404_for_unknown_slug(self):
        response = self.client.get(
            reverse("api_district_stats", kwargs={"district_slug": "does-not-exist"})
        )
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Phase 6C — District HTML pages
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class DistrictPageTests(TestCase):
    def setUp(self):
        self.district = District.objects.create(
            name="Test District",
            slug="test-district",
            geometry=TEST_DISTRICT_GEOM,
        )

    def test_districts_list_page_is_public(self):
        response = self.client.get(reverse("districts"))
        self.assertEqual(response.status_code, 200)

    def test_district_detail_page_is_public(self):
        response = self.client.get(
            reverse("district_detail", kwargs={"district_slug": "test-district"})
        )
        self.assertEqual(response.status_code, 200)

    def test_district_detail_page_404_for_inactive(self):
        District.objects.create(
            name="Inactive District",
            slug="inactive-d",
            geometry=TEST_DISTRICT_GEOM,
            active=False,
        )
        response = self.client.get(
            reverse("district_detail", kwargs={"district_slug": "inactive-d"})
        )
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Preferences API (multi-county)
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=False)
class PreferencesApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pref-user", password="pass12345")

    def test_preferences_requires_auth(self):
        response = self.client.get(reverse("api_preferences"))
        self.assertEqual(response.status_code, 302)

    def test_preferences_get_shape(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api_preferences"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for key in ("default_counties", "visible_district_slugs", "public_profile"):
            self.assertIn(key, data)
        self.assertIsInstance(data["default_counties"], list)

    def test_preferences_save_default_counties(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_preferences"),
            data=json.dumps({"default_counties": ["Putnam", "White"], "visible_district_slugs": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        pref = UserMapPreference.objects.get(user=self.user)
        self.assertEqual(pref.default_counties, ["Putnam", "White"])

    def test_preferences_save_visible_slugs(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("api_preferences"),
            data=json.dumps({"default_counties": [], "visible_district_slugs": ["district-1"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        pref = UserMapPreference.objects.get(user=self.user)
        self.assertEqual(pref.visible_district_slugs, ["district-1"])

    def test_preferences_empty_counties_saves_empty_list(self):
        self.client.force_login(self.user)
        # First save some counties
        self.client.post(
            reverse("api_preferences"),
            data=json.dumps({"default_counties": ["Putnam"], "visible_district_slugs": []}),
            content_type="application/json",
        )
        # Then clear them
        self.client.post(
            reverse("api_preferences"),
            data=json.dumps({"default_counties": [], "visible_district_slugs": []}),
            content_type="application/json",
        )
        pref = UserMapPreference.objects.get(user=self.user)
        self.assertEqual(pref.default_counties, [])
