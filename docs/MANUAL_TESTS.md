# Manual Test Scripts

Repeatable manual scripts mapped 1:1 to `docs/QA_MATRIX.md`.

## Preconditions
- Test environment has running PostGIS and Django app.
- At least one valid login account exists.
- For API tests, you are logged in through browser session or have session+CSRF cookies.

## MT-001 Authentication Required for Map and API
Related feature: `F-001`

Steps:
1. Open a private/incognito browser window.
2. Visit `/map/`.
3. Visit `/api/features/` directly.
4. Log in at `/accounts/login/`, then revisit `/map/`.

Expected:
- Unauthenticated requests redirect to login.
- Authenticated user can access map and API.

## MT-002 Map Loads and Basemap UI
Related feature: `F-002`

Steps:
1. Log in.
2. Open `/map/`.
3. Confirm map container, side panel, and buttons render.
4. Pan/zoom and verify map tiles load.

Expected:
- Map opens near Putnam/Cookeville area.
- Side controls and basemap are visible and usable.

## MT-003 Browse/List Features with Filters
Related feature: `F-003`

Steps:
1. Ensure at least one trash site and one route exist.
2. On `/map/`, toggle status checkboxes and click `Apply Filters`.
3. Switch date range between `7`, `30`, and `all`.
4. Pan to a different area and back.

Expected:
- Feature set updates after filter changes and map movement.
- Hidden statuses are removed from current map rendering.

## MT-004 Create TrashSite Item
Related feature: `F-004`

Steps:
1. Click `Report Trash`.
2. Click a point on the map.
3. Fill optional fields (title/description/severity/hazard).
4. Attach one image and submit.

Expected:
- New marker appears.
- Opening details shows entered fields and uploaded photo.

## MT-005 View TrashSite Detail and Proofs
Related feature: `F-005`

Steps:
1. Click an existing trash marker.
2. Confirm detail panel values (status/severity/hazard/description).
3. Confirm proof history section and images render.

Expected:
- Detail panel populates from API and includes proof content.

## MT-006 Mark TrashSite Cleaned
Related feature: `F-006`

Steps:
1. Open a `PENDING` trash site detail.
2. Click `Mark Cleaned`.
3. Enter note + bags_count, attach photo, submit.
4. Reopen same marker detail.

Expected:
- Status changes to `CLEANED`.
- Cleanup proof appears with note, bags_count, and photo.

## MT-007 Edit TrashSite via API (PATCH)
Related feature: `F-007`

Steps:
1. Capture a trash site ID from detail payload (or admin URL).
2. Send PATCH to `/api/trash-sites/<id>/` with updated fields (for example status/title).
3. Reload map and open that marker.

Expected:
- API returns updated values.
- Marker detail reflects updated fields.

## MT-008 Create RouteCleanup Item
Related feature: `F-008`

Steps:
1. Click `Log Cleanup Route`.
2. Draw a polyline with at least 2 points.
3. Fill notes/time and submit.

Expected:
- New route line appears on map.
- Route persists after refresh.

## MT-009 Route Detail and Distance Display
Related feature: `F-009`

Steps:
1. Click a route line.
2. Verify detail panel shows notes, time, and distance.
3. Compare popup distance summary to detail distance.

Expected:
- Distance is displayed and greater than zero for valid non-trivial route.

## MT-010 Admin CRUD and Delete Item
Related feature: `F-010`

Steps:
1. Log in as superuser at `/admin/`.
2. Open TrashSite or RouteCleanup list.
3. Edit a record and save.
4. Delete a record via admin.
5. Return to `/map/` and refresh features.

Expected:
- Record updates are saved.
- Deleted record no longer appears on map.

## MT-011 Geometry Convention and SRID Sanity Check
Related feature: `F-011`

Steps:
1. Create one trash site and one route.
2. Open detail JSON endpoints.
3. Verify coordinate order is `[lng, lat]` in returned payloads.
4. In admin GIS map, verify locations render in expected area (Putnam County vicinity).

Expected:
- Coordinates are consistently `[lng, lat]`.
- Geometry renders in the expected map region.

## MT-012 Route Distance Calculation Validation
Related feature: `F-012`

Steps:
1. Draw a short route (2-3 points).
2. Save route and read `distance_miles` in route detail.
3. Draw a noticeably longer route and save.
4. Compare distances.

Expected:
- Longer route has larger `distance_miles`.
- Distances are non-zero for valid lines.

## MT-013 Proof/Photo Upload and Retrieval
Related feature: `F-013`

Steps:
1. Upload photo while creating a trash site or marking cleaned.
2. Open detail panel and verify image is shown.
3. Open image URL in new browser tab.

Expected:
- Image URL resolves and image loads.
- Proof references are visible in detail payload/UI.

## MT-014 API Surface Smoke Test
Related feature: `F-014`

Steps:
1. Hit each implemented endpoint with authenticated session:
   - `/api/features/`
   - `/api/trash-sites/<id>/`
   - `/api/trash-sites/<id>/detail/`
   - `/api/route-cleanups/<id>/detail/`
2. Validate status code and minimal shape of response.

Expected:
- Endpoints return 2xx for valid authenticated requests.
- Combined features payload includes both `trash_site` and `route_cleanup` types (when data exists).

## MT-015 Geometry and Payload Validation Errors
Related feature: `F-015`

Steps:
1. POST `/api/route-cleanups/` with invalid coordinates (`[]` or one point).
2. POST `/api/trash-sites/` with invalid severity.
3. PATCH trash site with invalid status.

Expected:
- Server returns non-2xx with JSON body containing `error`.

## MT-016 Docker Up Workflow
Related feature: `F-016`

Steps:
1. Run `docker compose up --build -d`.
2. Check `docker ps`.
3. Check web logs.
4. Open app in browser.

Expected:
- `db` is healthy and `web` is running.
- Web logs show migrations and server startup.

## MT-017 Local Python Run Workflow
Related feature: `F-017`

Steps:
1. Start DB only: `docker compose up -d db`.
2. Activate venv and install requirements.
3. Set env vars from `.env.example`.
4. Run `python manage.py migrate` then `python manage.py runserver`.
5. Run `python manage.py test`.

Expected:
- Local server starts and app is reachable.
- Django test suite runs with no import/runtime errors.

## MT-018 Diagnostics and Error Visibility
Related feature: `F-018`

Steps:
1. Trigger a known API validation error (for example MT-015 step 1).
2. In browser, attempt invalid action and observe UI feedback.
3. Inspect `docker compose logs web`.

Expected:
- API returns readable JSON error.
- UI shows failure signal (alert or detail text).
- Logs capture request/response context for debugging.
