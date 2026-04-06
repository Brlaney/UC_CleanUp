# Current Features (As-Is)

This file documents implemented behavior in the current codebase only.

## Core User Flows

### F-001 Public / Authenticated Access Control
- Map (`/`) and cleanups page (`/cleanups/`) are publicly accessible.
- Public JSON endpoints: `/api/features/`, `/api/districts/`, `/api/trash-sites/<id>/detail/`, `/api/cleanups/`.
- Write endpoints require login: `POST /api/trash-sites/`, `PATCH /api/trash-sites/<id>/`, `POST mark-cleaned`, `POST feedback`.
- Signup available at `/accounts/signup/`; login at `/accounts/login/`.
- Done when:
  - Unauthenticated users can view map, features, and cleanups.
  - Write operations redirect to login when unauthenticated.

### F-002 Map Initialization and District Boundary
- `/` renders a full Leaflet map view.
- District boundary is loaded dynamically from `/api/districts/` API (not a static file).
- Outside-district area is masked with a semi-transparent overlay.
- Map fits bounds to the active district on load.
- Done when:
  - Public user sees map with district boundary overlay and masked exterior.

### F-003 Two-Mode Map UI
- Mode switcher at top of control panel: **Report Trash** / **Cleanup Trash**.
- **Report mode**: Place Pin or Draw Area sub-modes.
  - Place Pin: click map to set a point location.
  - Draw Area: activate leaflet-draw polygon tool.
- **Cleanup mode**: click existing markers to view detail and mark cleaned.
  - Status filter chips (Pending / In Progress / Cleaned).
- Auth gate overlay appears when unauthenticated user attempts to interact.
- Done when:
  - Mode switching updates panel, ARIA states, and map interaction behavior.
  - Auth gate blocks submissions for anonymous users.

### F-004 Feature Loading with BBox + Filters
- Frontend requests `GET /api/features/` using:
  - `bbox=minLng,minLat,maxLng,maxLat`
  - `status` CSV
  - `days` (`7`, `30`, `all`)
  - `district` slug
- Features reload on map `moveend`.
- Backend returns `FeatureCollection` with trash site point features.
- Done when:
  - Moving map or applying filters updates rendered markers.

### F-005 Create TrashSite (Point or Polygon)
- Report mode: click map for point, or draw polygon for area report.
- Polygon reports auto-compute centroid for the location field.
- Modal form posts multipart data to `POST /api/trash-sites/`.
- Optional fields: title, description, severity, hazard flag, photos (max 5).
- District is auto-assigned via spatial query.
- Done when:
  - New marker appears after submit. Area reports show polygon overlay.

### F-006 View TrashSite Details
- Clicking a trash marker loads detail from `GET /api/trash-sites/<id>/detail/`.
- Detail panel shows status, severity, hazard flag, description, photos grouped by type (report/before/after), and proof history.
- Done when:
  - Marker click loads full detail with grouped photos and proof list.

### F-007 Mark TrashSite Cleaned with Before/After Photos
- `Mark Cleaned` action posts to `POST /api/trash-sites/<id>/mark-cleaned/`.
- Creates `CleanupProof` with note, bag count, before photos, and after photos.
- Sets `TrashSite.status = CLEANED` and `cleaned_at = now`.
- Before/after photos are stored with separate `photo_type` values.
- Done when:
  - Marker status updates to cleaned. Proof with before/after photos appears in detail.

### F-008 Edit TrashSite via PATCH API
- `PATCH /api/trash-sites/<id>/` supports updates for:
  - `status`, `title`, `description`, `severity`, `hazard_flag`
- Cleaning timestamp is managed based on status transitions.
- Done when:
  - PATCH updates fields and response reflects updated values.

### F-009 Public Cleanups Showcase
- `/cleanups/` displays completed cleanups with before/after photo galleries.
- `GET /api/cleanups/` returns paginated cleaned sites with grouped photos.
- Done when:
  - Public visitors can browse completed cleanups without login.

### F-010 Admin Management
- Django admin enabled for `District`, `TrashSite`, `CleanupProof`, `Photo`, `Profile`, `ActivityLog`, `FeedbackEntry`, `IPBan`.
- GIS admin used for spatial models.
- Done when:
  - Admin user can manage all records.

### F-011 In-App Feedback Reporting
- Authenticated users submit `BUG`, `REQUEST`, or `GENERAL` feedback from top bar modal.
- Stored in `FeedbackEntry`.
- Done when:
  - Feedback submits without leaving the app.

### F-012 Role-Aware TrashSite Permissions
- `Profile` records support `MEMBER` and `ADMIN` roles.
- TrashSite PATCH editing limited to creator or admin.
- Setting status to `INVALID` limited to admins.
- Marking cleaned available to any authenticated user unless site is `INVALID`.
- Done when:
  - Unauthorized edits rejected with 403.

## District Abstraction

### F-013 District Model and API
- `District` model stores name, slug, MultiPolygon geometry, active flag.
- `GET /api/districts/` returns active districts with GeoJSON geometry.
- Trash sites auto-assigned to districts via `geometry__covers` spatial query.
- Designed for future multi-district support.
- Done when:
  - District boundary loads from API. Sites are assigned to districts on creation.

## Security and Anti-Abuse

### F-014 Rate Limiting
- `django-ratelimit` decorators on all API endpoints.
- Per-IP limits on read endpoints; per-user limits on write endpoints.
- Optional Redis backend via `REDIS_URL`; defaults to in-memory cache.
- Done when:
  - Exceeding rate limits returns 403.

### F-015 IP Ban Middleware
- `IPBanMiddleware` checks every request against `IPBan` table.
- Supports permanent bans (null expiry) and temporary bans with expiry.
- Uses `X-Forwarded-For` header with fallback to `REMOTE_ADDR`.
- Done when:
  - Banned IPs receive 403. Expired bans are ignored.

### F-016 Photo Upload Validation
- Server-side validation: max 5 files, 10 MB each, image MIME types only (JPEG, PNG, WebP, HEIC).
- Applied on report creation and cleanup proof submission.
- Done when:
  - Oversized, over-count, or wrong-type uploads are rejected.

## Data + Geometry Rules

### F-017 Spatial Model Standards
- `TrashSite.location` = `PointField(geography=True, srid=4326)`
- `TrashSite.area` = `PolygonField(geography=True, srid=4326)` (optional)
- `District.geometry` = `MultiPolygonField(geography=True, srid=4326)`
- UUID primary keys on domain models.
- Coordinate convention: `[lng, lat]`.
- Done when:
  - All geometry uses SRID 4326 and `[lng, lat]` order.

### F-018 Proof + Photo Evidence Linkage
- `CleanupProof` attaches to `TrashSite`.
- `Photo` attaches to `CleanupProof` with `photo_type` (REPORT/BEFORE/AFTER).
- Done when:
  - Photos are grouped by type in detail responses.

## Accessibility

### F-019 Accessibility Features
- Skip-to-content link.
- ARIA roles on all modals (`role="dialog"`, `aria-modal="true"`).
- Focus trap and return on modal open/close.
- `aria-live` regions for toasts, detail panel, and mode instructions.
- WCAG 2.1 AA color contrast compliance.
- Keyboard navigable map controls.
- Done when:
  - Screen reader announces mode changes, submissions, and errors.
  - Tab navigation works within modals without escaping.

## API

### F-020 API Surface
- Public endpoints:
  - `GET /healthz`
  - `GET /api/features/?bbox=&status=&days=&district=`
  - `GET /api/districts/`
  - `GET /api/trash-sites/<id>/detail/`
  - `GET /api/cleanups/?page=&page_size=`
- Authenticated endpoints:
  - `POST /api/trash-sites/`
  - `PATCH /api/trash-sites/<id>/`
  - `POST /api/trash-sites/<id>/mark-cleaned/`
  - `POST /api/feedback/`
- Done when:
  - All endpoints return expected JSON shapes.

### F-021 API Validation and Error Payloads
- Invalid inputs return JSON errors (invalid severity, bad coordinates, invalid status).
- Photo validation enforced on upload endpoints.
- Done when:
  - Invalid requests return non-2xx with `{"error": ...}`.

## Dev/Ops

### F-022 Dockerized Development Stack
- `docker-compose.yml`: `db` (PostGIS 16) + `web` (Django with GDAL/GEOS/PROJ).
- Entrypoint waits for DB, runs migrations, seeds district data, collects static, starts server.
- Done when:
  - `docker compose up --build -d` boots healthy stack with seeded district.

### F-023 Signup Flow
- `/accounts/signup/` with Django `UserCreationForm`.
- Auto-login after successful registration, redirect to map.
- Authenticated users redirected away from signup page.
- Done when:
  - New users can register and immediately use the app.

## Observability

### F-024 Runtime Diagnostics
- `GET /healthz` reports application/database readiness.
- API errors return explicit JSON.
- Frontend uses toast notifications for success/error feedback.
- Done when:
  - Failures visible without debugger.
