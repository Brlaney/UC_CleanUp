# Current Features (As-Is)

This file documents implemented behavior in the current codebase only.  
Future ideas and design planning are tracked separately in `docs/UI_ROADMAP.md`.

## Core User Flows

### F-001 Authenticated Access Control
- Django auth is enabled at `/accounts/login/`.
- Root path `/` redirects to `/map/`.
- Map, updates, impact, and private API endpoints are protected with `@login_required`.
- Logout is available in the top bar.
- Done when:
  - Unauthenticated users are redirected to login for protected HTML routes and `/api/...`.
  - Authenticated users can access map and API.

### F-002 Map Initialization and Basemap UX
- `/map/` renders a full map view using Leaflet.
- Map default center is near Cookeville (`[36.1627, -85.5016]`) with zoom 12.
- OpenStreetMap tiles are loaded.
- County boundary overlays support Putnam-only, a six-county TN preset (`Smith`, `Jackson`, `Putnam`, `White`, `Van Buren`, `Cumberland`), full Upper Cumberland, and custom county selection.
- Side panel includes filters, actions, and detail area.
- Done when:
  - Logged-in user sees map, controls, and basemap tiles.
  - Changing county overlay presets swaps the highlighted boundaries without clearing cleanup overlays.

### F-003 Shared Feature Loading with BBox + Filters
- Frontend requests `GET /api/features/` using:
  - `bbox=minLng,minLat,maxLng,maxLat`
  - `status` CSV
  - `days` (`7`, `30`, `all`)
- Features reload on map `moveend` and `zoomend`.
- Backend returns one `FeatureCollection` with both point and line features.
- Done when:
  - Moving map or applying filters updates rendered points/lines.

### F-004 Create TrashSite from Map
- User clicks `Report Trash`, then clicks map to set point.
- Modal form posts multipart data to `POST /api/trash-sites/`.
- Optional fields: title, description, severity, hazard flag, photos.
- New site is created with default status `PENDING`.
- Done when:
  - New marker appears after submit and persists on refresh.

### F-005 View TrashSite Details and Proof History
- Clicking a trash marker loads detail from `GET /api/trash-sites/<id>/detail/`.
- Detail panel shows status, severity, hazard flag, description, and proofs.
- Proof photos are displayed in detail panel.
- Done when:
  - Marker click loads full detail including proof list and image thumbnails.

### F-006 Mark TrashSite Cleaned with Proof
- `Mark Cleaned` action posts to `POST /api/trash-sites/<id>/mark-cleaned/`.
- Creates `CleanupProof` with note, bag count, optional photos.
- Sets `TrashSite.status = CLEANED` and `cleaned_at = now`.
- Done when:
  - Marker color/status updates to cleaned and proof appears in details.

### F-007 Edit TrashSite via PATCH API
- `PATCH /api/trash-sites/<id>/` supports updates for:
  - `status`
  - `title`
  - `description`
  - `severity`
  - `hazard_flag`
- Cleaning timestamp is managed based on status transitions.
- Done when:
  - PATCH updates fields and response reflects updated values.

### F-008 Create RouteCleanup Polyline
- `Log Cleanup Route` enables leaflet-draw polyline mode.
- Drawn line coordinates are submitted to `POST /api/route-cleanups/`.
- Optional fields: notes, time_spent_minutes, photos.
- Done when:
  - Saved route appears on map after submit.

### F-009 View RouteCleanup Details
- Clicking route line loads detail from `GET /api/route-cleanups/<id>/detail/`.
- Detail panel shows notes, status, time spent, and distance in miles.
- Done when:
  - Route click shows detail and distance value.

### F-010 Admin Management (Including Delete)
- Django admin is enabled for `TrashSite`, `RouteCleanup`, `CleanupProof`, `Photo`, `Profile`, `ActivityLog`, and `FeedbackEntry`.
- GIS admin is used for spatial models.
- Admin supports edit/search/filter and delete operations.
- Done when:
  - Admin user can create/edit/delete records and map reflects deletions.

### F-019 Activity Updates Feed
- `/updates/` shows recent activity across reports, cleanup proofs, and route logging.
- `GET /api/activity/` returns paginated activity entries with map focus metadata.
- Activity cards link back to `/map/` with `focus_type` and `focus_id` query parameters.
- Done when:
  - Logged-in user can open `/updates/`, see recent events, and jump to the relevant map feature.

### F-020 Personal Impact Dashboard
- `/impact/` shows contribution totals for the current user.
- Totals include:
  - reported sites
  - cleaned sites
  - bags collected
  - logged routes
  - route miles
  - minutes logged
- Done when:
  - Logged-in user can open `/impact/` and see their contribution summary.

### F-021 In-App Feedback Reporting
- Authenticated users can submit `BUG`, `REQUEST`, or `GENERAL` feedback from the top bar modal.
- Feedback is stored in `FeedbackEntry` and managed through Django admin.
- Submitted feedback includes free-text message and current page URL.
- Done when:
  - Logged-in user can send feedback without leaving the app and admins can review it later.

### F-022 Role-Aware TrashSite Permissions
- `Profile` records support `MEMBER` and `ADMIN` roles.
- TrashSite PATCH editing is limited to creator or admin.
- Setting TrashSite status to `INVALID` is limited to admins.
- Marking a site cleaned remains available to authenticated users unless the site is already `INVALID`.
- Done when:
  - Unauthorized edits are rejected with 403 JSON errors.
  - Admin-only invalidation is enforced.

## Data + Geometry Rules

### F-011 Spatial Model Standards
- Spatial fields:
  - `TrashSite.location` = `PointField(geography=True, srid=4326)`
  - `RouteCleanup.geometry` = `LineStringField(geography=True, srid=4326)`
- UUID primary keys are used for domain models.
- Spatial indexes are enabled on geometry fields.
- Coordinate convention is `[lng, lat]`.
- Done when:
  - Stored and returned geometry consistently uses SRID 4326 and `[lng, lat]`.

### F-012 Server-Side Route Distance Calculation
- `RouteCleanup.save()` computes line length in meters using Haversine segment sum.
- Conversion uses `distance_miles = meters * 0.000621371`.
- Distance recalculates on save when geometry is present.
- Done when:
  - Persisted routes have non-zero `distance_miles` for valid multi-point lines.

### F-013 Proof + Photo Evidence Linkage
- `CleanupProof` attaches to either `TrashSite` or `RouteCleanup`.
- `Photo` attaches to `CleanupProof`.
- Upload storage uses local `MEDIA_ROOT`; URLs exposed via serializers.
- Done when:
  - Uploaded images are retrievable and visible in detail views.

## API

### F-014 Authenticated API Surface
- Implemented JSON routes:
  - `GET /healthz`
  - `GET /api/features/`
  - `GET /api/activity/`
  - `POST /api/feedback/`
  - `POST /api/trash-sites/`
  - `GET|PATCH /api/trash-sites/<id>/`
  - `GET /api/trash-sites/<id>/detail/`
  - `POST /api/trash-sites/<id>/mark-cleaned/`
  - `POST /api/route-cleanups/`
  - `GET /api/route-cleanups/<id>/`
  - `GET /api/route-cleanups/<id>/detail/`
- Combined feature response includes `properties.type` (`trash_site` or `route_cleanup`).
- Done when:
  - Endpoints return expected payloads for authenticated user sessions.

### F-015 API Validation and Error Payloads
- Invalid inputs return JSON errors (e.g., invalid severity, bad coordinates, invalid status).
- Route creation validates minimum coordinate count and GeoJSON line type.
- Done when:
  - Invalid requests return non-2xx with an `{"error": ...}` payload.

## Dev/Ops

### F-016 Dockerized Development Stack
- `docker-compose.yml` includes:
  - `db` (`postgis/postgis:16-3.4`)
  - `web` (Django app image with GDAL/GEOS/PROJ installed)
- Entry point waits for DB, runs migrations, optionally collects static files, then starts:
  - Django `runserver` in debug
  - Gunicorn when `DEBUG=0`
- Host web port is configurable with `WEB_PORT`.
- Done when:
  - `docker compose up --build -d` boots healthy DB + running web app.

### F-017 Local Python Runtime + Config
- Settings are environment-driven for DB/auth/static/media/security/storage.
- Local media served in DEBUG mode.
- Object storage is supported via S3-compatible settings for production media.
- Database config supports `DATABASE_URL` as well as individual `POSTGRES_*` variables.
- Django test suite exists via `python manage.py test`.
- No pytest configuration is present in the repo.
- Done when:
  - Local run works with env vars and `manage.py test` executes.

### F-023 Visual Screenshot Capture Workflow
- Playwright can capture a repeatable screenshot gallery for desktop and mobile form factors.
- `python manage.py seed_screenshot_demo` creates deterministic demo records and a dedicated screenshot user.
- `scripts/capture-screenshots.ps1` starts the Docker stack, runs migrations, seeds demo data, and writes screenshots to `artifacts/screenshots/`.
- Done when:
  - One command produces current screenshots for desktop and phone-sized layouts without manual browser resizing.

## Observability / Troubleshooting

### F-018 Runtime Diagnostics and Error Visibility
- Container startup logs show DB wait, migration run, static collection, and server start.
- API errors are explicit JSON (`{"error": ...}`).
- Frontend surfaces request failures in alert dialogs or detail panel text.
- `GET /healthz` reports basic application/database readiness.
- Done when:
  - Failures are visible to developers/users without attaching a debugger.
