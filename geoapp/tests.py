import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import LineString, Point
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CleanupProof, RouteCleanup, TrashSite


class AuthGateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="auth-user", password="pass12345")

    def test_unauthenticated_map_redirects_to_login(self):
        response = self.client.get(reverse("map"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_unauthenticated_api_endpoint_redirects_to_login(self):
        response = self.client.get(reverse("api_features"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_authenticated_map_and_api_access_succeed(self):
        self.client.force_login(self.user)
        map_response = self.client.get(reverse("map"))
        api_response = self.client.get(reverse("api_features"))
        self.assertEqual(map_response.status_code, 200)
        self.assertEqual(api_response.status_code, 200)
        payload = api_response.json()
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertIn("features", payload)


class RouteCleanupModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="route-user", password="pass12345")

    def test_distance_miles_is_computed_from_geometry(self):
        route = RouteCleanup.objects.create(
            geometry=LineString((-85.5010, 36.1627), (-85.4910, 36.1627), srid=4326),
            notes="Roadside cleanup",
            created_by=self.user,
        )
        self.assertGreater(route.distance_miles, 0)
        self.assertAlmostEqual(route.distance_miles, 0.56, delta=0.2)


class MarkCleanedApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cleanup-user", password="pass12345")
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


class TrashSiteApiLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="trash-user", password="pass12345")
        self.client.force_login(self.user)

    def test_create_trash_site_returns_expected_fields_and_geometry(self):
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
        self.assertAlmostEqual(site.location.x, -85.5016, places=6)
        self.assertAlmostEqual(site.location.y, 36.1627, places=6)

    def test_patch_trash_site_updates_fields_and_cleaned_at_transitions(self):
        site = TrashSite.objects.create(
            location=Point(-85.5000, 36.1600, srid=4326),
            status=TrashSite.Status.PENDING,
            title="Initial title",
            description="Initial description",
            created_by=self.user,
        )

        cleaned_payload = {
            "status": TrashSite.Status.CLEANED,
            "title": "Updated title",
            "description": "Updated description",
            "severity": TrashSite.Severity.HEAVY,
            "hazard_flag": True,
        }
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": site.id}),
            data=json.dumps(cleaned_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        cleaned_response = response.json()
        self.assertEqual(cleaned_response["status"], TrashSite.Status.CLEANED)
        self.assertEqual(cleaned_response["title"], "Updated title")
        self.assertEqual(cleaned_response["severity"], TrashSite.Severity.HEAVY)
        self.assertTrue(cleaned_response["hazard_flag"])
        self.assertIsNotNone(cleaned_response["cleaned_at"])

        pending_payload = {"status": TrashSite.Status.PENDING}
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": site.id}),
            data=json.dumps(pending_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        pending_response = response.json()
        self.assertEqual(pending_response["status"], TrashSite.Status.PENDING)
        self.assertIsNone(pending_response["cleaned_at"])


class FeaturesFilterApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="filter-user", password="pass12345")
        self.client.force_login(self.user)

        self.in_bbox_pending = TrashSite.objects.create(
            location=Point(-85.5020, 36.1630, srid=4326),
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )
        self.in_bbox_cleaned_recent = TrashSite.objects.create(
            location=Point(-85.4995, 36.1620, srid=4326),
            status=TrashSite.Status.CLEANED,
            created_by=self.user,
        )
        self.in_bbox_cleaned_old = TrashSite.objects.create(
            location=Point(-85.4980, 36.1610, srid=4326),
            status=TrashSite.Status.CLEANED,
            created_by=self.user,
        )
        TrashSite.objects.filter(id=self.in_bbox_cleaned_old.id).update(created_at=timezone.now() - timedelta(days=10))
        self.in_bbox_cleaned_old.refresh_from_db()

        self.out_of_bbox = TrashSite.objects.create(
            location=Point(-85.7000, 36.3000, srid=4326),
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )

    def _trash_site_ids(self, payload):
        return {
            feature["properties"]["id"]
            for feature in payload["features"]
            if feature["properties"]["type"] == "trash_site"
        }

    def test_bbox_returns_only_in_bounds_features(self):
        response = self.client.get(
            reverse("api_features"),
            {"bbox": "-85.51,36.15,-85.49,36.17", "days": "all"},
        )
        self.assertEqual(response.status_code, 200)
        ids = self._trash_site_ids(response.json())
        self.assertIn(str(self.in_bbox_pending.id), ids)
        self.assertIn(str(self.in_bbox_cleaned_recent.id), ids)
        self.assertIn(str(self.in_bbox_cleaned_old.id), ids)
        self.assertNotIn(str(self.out_of_bbox.id), ids)

    def test_status_and_date_filters_return_expected_subset(self):
        cleaned_response = self.client.get(
            reverse("api_features"),
            {"bbox": "-85.51,36.15,-85.49,36.17", "status": "CLEANED", "days": "all"},
        )
        self.assertEqual(cleaned_response.status_code, 200)
        cleaned_ids = self._trash_site_ids(cleaned_response.json())
        self.assertNotIn(str(self.in_bbox_pending.id), cleaned_ids)
        self.assertIn(str(self.in_bbox_cleaned_recent.id), cleaned_ids)
        self.assertIn(str(self.in_bbox_cleaned_old.id), cleaned_ids)

        recent_cleaned_response = self.client.get(
            reverse("api_features"),
            {"bbox": "-85.51,36.15,-85.49,36.17", "status": "CLEANED", "days": "7"},
        )
        self.assertEqual(recent_cleaned_response.status_code, 200)
        recent_cleaned_ids = self._trash_site_ids(recent_cleaned_response.json())
        self.assertIn(str(self.in_bbox_cleaned_recent.id), recent_cleaned_ids)
        self.assertNotIn(str(self.in_bbox_cleaned_old.id), recent_cleaned_ids)


class RouteCleanupApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="route-api-user", password="pass12345")
        self.client.force_login(self.user)

    def test_create_route_get_detail_and_list_in_features_bbox(self):
        create_response = self.client.post(
            reverse("api_route_cleanup_create"),
            data=json.dumps(
                {
                    "coordinates": [[-85.5010, 36.1620], [-85.4980, 36.1630], [-85.4950, 36.1640]],
                    "notes": "Road shoulder cleanup",
                    "time_spent_minutes": 35,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        route_id = created["id"]
        self.assertIn("distance_miles", created)
        self.assertGreater(created["distance_miles"], 0)

        detail_response = self.client.get(reverse("api_route_cleanup_detail_root", kwargs={"route_id": route_id}))
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["id"], route_id)
        self.assertGreater(detail["distance_miles"], 0)
        self.assertGreaterEqual(len(detail["coordinates"]), 2)

        feature_response = self.client.get(
            reverse("api_features"),
            {"bbox": "-85.51,36.15,-85.49,36.17", "days": "all"},
        )
        self.assertEqual(feature_response.status_code, 200)
        route_ids = {
            feature["properties"]["id"]
            for feature in feature_response.json()["features"]
            if feature["properties"]["type"] == "route_cleanup"
        }
        self.assertIn(route_id, route_ids)


class ApiSurfaceContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="contract-user", password="pass12345")
        self.client.force_login(self.user)
        self.site = TrashSite.objects.create(
            location=Point(-85.5016, 36.1627, srid=4326),
            status=TrashSite.Status.PENDING,
            created_by=self.user,
        )
        self.route = RouteCleanup.objects.create(
            geometry=LineString((-85.5010, 36.1620), (-85.4980, 36.1630), srid=4326),
            created_by=self.user,
        )

    def test_core_get_endpoints_return_expected_json_shapes(self):
        features_response = self.client.get(
            reverse("api_features"),
            {"bbox": "-85.51,36.15,-85.49,36.17", "days": "all"},
        )
        self.assertEqual(features_response.status_code, 200)
        features_payload = features_response.json()
        self.assertEqual(features_payload["type"], "FeatureCollection")
        self.assertIn("features", features_payload)

        trash_response = self.client.get(reverse("api_trash_site_update", kwargs={"site_id": self.site.id}))
        self.assertEqual(trash_response.status_code, 200)
        trash_payload = trash_response.json()
        self.assertEqual(trash_payload["id"], str(self.site.id))
        self.assertIn("status", trash_payload)
        self.assertIn("coordinates", trash_payload)

        route_response = self.client.get(reverse("api_route_cleanup_detail_root", kwargs={"route_id": self.route.id}))
        self.assertEqual(route_response.status_code, 200)
        route_payload = route_response.json()
        self.assertEqual(route_payload["id"], str(self.route.id))
        self.assertIn("distance_miles", route_payload)
        self.assertIn("coordinates", route_payload)


class ApiValidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="validation-user", password="pass12345")
        self.client.force_login(self.user)
        self.site = TrashSite.objects.create(
            location=Point(-85.5016, 36.1627, srid=4326),
            created_by=self.user,
        )

    def test_invalid_route_geometry_payload_returns_json_error(self):
        response = self.client.post(
            reverse("api_route_cleanup_create"),
            data=json.dumps({"coordinates": [[-85.50, 36.16]]}),
            content_type="application/json",
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_invalid_trash_status_patch_returns_json_error(self):
        response = self.client.patch(
            reverse("api_trash_site_update", kwargs={"site_id": self.site.id}),
            data=json.dumps({"status": "NOT_A_REAL_STATUS"}),
            content_type="application/json",
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertIn("error", response.json())
