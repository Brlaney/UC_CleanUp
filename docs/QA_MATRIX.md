# QA Matrix

Coverage inventory for implemented features.
Feature IDs are sourced from `docs/FEATURES.md`.

| ID | Feature | Auto Tests | Manual Tests | Test Locations | Notes |
|---|---|---|---|---|---|
| F-001 | Public / authenticated access control | ✅ | ⚠️ | `tests.py::PublicAccessTests`, `tests.py::AuthGateTests` | Map and read APIs are public; write endpoints require login. |
| F-002 | Map initialization and district boundary | ⚠️ | ⚠️ | `e2e/map-smoke.spec.js` | Smoke covers map load; district boundary from API needs manual check. |
| F-003 | Two-mode map UI | ❌ | ⚠️ | N/A | Frontend mode switching is manual-only. |
| F-004 | Feature loading with bbox + filters | ✅ | ⚠️ | `tests.py::FeaturesFilterApiTests` | Covers bbox, status, days, and district filters. |
| F-005 | Create TrashSite (point or polygon) | ✅ | ⚠️ | `tests.py::TrashSiteApiLifecycleTests`, `tests.py::TrashSitePolygonTests` | Point, GeoJSON point, polygon creation, and district auto-assignment. |
| F-006 | View TrashSite details | ✅ | ⚠️ | `tests.py::TrashSiteApiLifecycleTests`, `tests.py::ApiSurfaceContractTests` | Detail API shape and public access verified. |
| F-007 | Mark TrashSite cleaned with before/after photos | ✅ | ⚠️ | `tests.py::MarkCleanedApiTests` | Covers status change, proof creation, and photo type separation. |
| F-008 | Edit TrashSite via PATCH | ✅ | ⚠️ | `tests.py::TrashSiteApiLifecycleTests` | Status transitions and cleaned_at management. |
| F-009 | Public cleanups showcase | ✅ | ⚠️ | `tests.py::CleanupsPageTests` | Page render, API filtering, and pagination. |
| F-010 | Admin management | ❌ | ⚠️ | N/A | Admin CRUD is manual-only. |
| F-011 | In-app feedback | ✅ | ⚠️ | `tests.py::FeedbackTests` | Submission and validation covered. |
| F-012 | Role-aware permissions | ✅ | ⚠️ | `tests.py::PermissionRoleTests` | Non-owner edit, non-admin invalidation, admin invalidation. |
| F-013 | District model and API | ✅ | ⚠️ | `tests.py::DistrictModelTests`, `tests.py::DistrictApiTests` | Creation, spatial assignment, active filtering, API shape. |
| F-014 | Rate limiting | ⚠️ | ⚠️ | N/A | Rate limits applied via decorators; most tests run with `RATELIMIT_ENABLE=False`. |
| F-015 | IP ban middleware | ✅ | ⚠️ | `tests.py::IPBanMiddlewareTests` | Permanent ban, expired ban, future expiry, XFF header. |
| F-016 | Photo upload validation | ✅ | ⚠️ | `tests.py::PhotoUploadValidationTests` | Count, size, and MIME type enforcement. |
| F-017 | Spatial model standards | ⚠️ | ⚠️ | Implicit in lifecycle tests | SRID and coordinate order verified through API responses. |
| F-018 | Proof + photo linkage | ✅ | ⚠️ | `tests.py::MarkCleanedApiTests`, `tests.py::ApiSurfaceContractTests` | Photo type grouping in detail response. |
| F-019 | Accessibility features | ❌ | ⚠️ | N/A | ARIA attributes in templates; manual/screen reader testing required. |
| F-020 | API surface | ✅ | ⚠️ | `tests.py::ApiSurfaceContractTests` | Shape validation for features, detail, cleanups, districts APIs. |
| F-021 | API validation and errors | ✅ | ⚠️ | `tests.py::ApiValidationTests` | Invalid status, severity, coordinates, and GeoJSON type. |
| F-022 | Dockerized dev stack | ❌ | ⚠️ | N/A | Manual Docker workflow only. |
| F-023 | Signup flow | ✅ | ⚠️ | `tests.py::SignupTests` | Page render, user creation, redirect, auth guard. |
| F-024 | Runtime diagnostics | ✅ | ⚠️ | `tests.py::PublicAccessTests` | Healthz endpoint automated. |
