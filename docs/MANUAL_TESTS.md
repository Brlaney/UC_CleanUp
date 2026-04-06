# Manual Test Scripts

Repeatable manual scripts mapped to `docs/QA_MATRIX.md`.

## Preconditions
- Test environment has running PostGIS and Django app.
- District 3 boundary is seeded (automatic on Docker startup).
- For write-endpoint tests, you have a logged-in browser session.

## MT-001 Public Map Access
Related feature: `F-001`

Steps:
1. Open a private/incognito browser window.
2. Visit `/`.
3. Visit `/cleanups/`.
4. Visit `/api/features/`.
5. Visit `/api/districts/`.

Expected:
- All pages load without login.
- Map shows district boundary and any existing features.

## MT-002 Auth Gate on Write Endpoints
Related feature: `F-001`

Steps:
1. Without logging in, click "Report Trash" on the map.
2. Try to interact (place pin or draw area).
3. Verify auth gate overlay appears.
4. Log in at `/accounts/login/`.
5. Retry the report action.

Expected:
- Unauthenticated users see auth gate overlay.
- After login, report submission works.

## MT-003 Map Initialization and District Boundary
Related feature: `F-002`

Steps:
1. Open `/`.
2. Confirm map loads with district boundary polygon.
3. Verify area outside district is masked/dimmed.
4. Confirm map fits to district bounds.

Expected:
- District boundary is visible and loaded from API.
- Outside area has semi-transparent overlay.

## MT-004 Two-Mode Switching
Related feature: `F-003`

Steps:
1. Open the map.
2. Click "Report Trash" mode button.
3. Verify report panel shows Place Pin / Draw Area buttons.
4. Click "Cleanup Trash" mode button.
5. Verify cleanup panel shows status filter chips.

Expected:
- Mode buttons toggle `aria-pressed` state.
- Panel content switches between report and cleanup modes.
- Screen reader announces mode change.

## MT-005 Report Trash - Place Pin
Related feature: `F-005`

Steps:
1. Log in and select Report Trash mode.
2. Click "Place Pin", then click on the map.
3. Fill title, description, severity, hazard flag.
4. Attach 1-3 photos and submit.

Expected:
- New marker appears on map.
- Toast notification confirms submission.
- Detail shows entered fields and uploaded photos.

## MT-006 Report Trash - Draw Area
Related feature: `F-005`

Steps:
1. Select Report Trash mode.
2. Click "Draw Area" and draw a polygon on the map.
3. Complete the polygon and fill the report form.
4. Submit.

Expected:
- Polygon overlay and centroid marker appear.
- Detail shows area geometry in response.

## MT-007 View TrashSite Detail
Related feature: `F-006`

Steps:
1. Click an existing trash marker.
2. Confirm detail panel shows status, severity, description.
3. Confirm photos are grouped into report/before/after sections.
4. Confirm proof history is listed.

Expected:
- Detail populates from API with grouped photo display.

## MT-008 Mark TrashSite Cleaned
Related feature: `F-007`

Steps:
1. In Cleanup mode, click a PENDING trash site marker.
2. Click "Mark Cleaned".
3. Upload before photo(s) and after photo(s).
4. Enter note and bags count, submit.
5. Recheck the marker.

Expected:
- Status changes to CLEANED.
- Before/after photos appear in detail grouped correctly.
- Site appears on `/cleanups/` page.

## MT-009 Edit TrashSite via PATCH
Related feature: `F-008`

Steps:
1. Get a trash site ID from detail panel.
2. Send PATCH to `/api/trash-sites/<id>/` with updated fields.
3. Reload map and check that marker detail reflects changes.

Expected:
- API returns updated values.
- Status transitions manage `cleaned_at` correctly.

## MT-010 Public Cleanups Page
Related feature: `F-009`

Steps:
1. Open `/cleanups/` without logging in.
2. Verify cleanup cards show title, severity, description, before/after photos.
3. If more than 12 cleanups exist, verify pagination works.

Expected:
- Page is publicly accessible.
- Before/after photo galleries render correctly.

## MT-011 Feature Filters
Related feature: `F-004`

Steps:
1. On the map, apply status filter (e.g., CLEANED only).
2. Switch date range between 7 days, 30 days, all.
3. Pan to a different area and back.

Expected:
- Feature set updates after filter changes and map movement.
- Only matching features are displayed.

## MT-012 Signup Flow
Related feature: `F-023`

Steps:
1. Visit `/accounts/signup/`.
2. Create a new account.
3. Verify redirect to map and auto-login.
4. While logged in, visit `/accounts/signup/` again.

Expected:
- New account is created and user is logged in.
- Already-authenticated users are redirected to `/`.

## MT-013 Role-Aware Permissions
Related feature: `F-012`

Steps:
1. Create a trash site as User A.
2. Log in as User B and try PATCH on User A's site.
3. Log in as User A and try setting status to INVALID.
4. Log in as admin user and set status to INVALID.

Expected:
- Non-owner gets 403 on PATCH.
- Non-admin gets 403 on invalidation.
- Admin can invalidate.

## MT-014 Feedback Submission
Related feature: `F-011`

Steps:
1. Log in and click "Feedback" in the top bar.
2. Submit a BUG type feedback with message.
3. Check admin for the created entry.

Expected:
- Feedback modal submits successfully.
- Entry stored with type, message, user, and page URL.

## MT-015 IP Ban Enforcement
Related feature: `F-015`

Steps:
1. Add an IP ban via Django admin.
2. Attempt to access any page from that IP.
3. Set an expiry in the past and retry.

Expected:
- Active ban returns 403 JSON response.
- Expired ban allows access.

## MT-016 Photo Upload Limits
Related feature: `F-016`

Steps:
1. Try uploading 6 photos in a report form.
2. Try uploading a file over 10 MB.
3. Try uploading a non-image file (e.g., PDF).

Expected:
- Server rejects with appropriate error message.

## MT-017 Docker Startup
Related feature: `F-022`

Steps:
1. Run `docker compose up --build -d`.
2. Check `docker ps` for healthy db + running web.
3. Check web logs for migrations, district seed, and server start.
4. Open app in browser.

Expected:
- Stack boots cleanly with district data auto-seeded.

## MT-018 Accessibility Checks
Related feature: `F-019`

Steps:
1. Tab through the page and verify skip-to-content link works.
2. Open a modal (report or feedback) and verify focus is trapped.
3. Press Escape to close modal and verify focus returns.
4. Use a screen reader to verify mode change announcements.
5. Check color contrast with a browser dev tools audit.

Expected:
- Focus management works correctly in all modals.
- ARIA live regions announce dynamic content changes.
- Colors meet WCAG 2.1 AA contrast requirements.

## MT-019 API Surface Smoke Test
Related feature: `F-020`

Steps:
1. Hit each endpoint and verify response shape:
   - `GET /api/features/` - FeatureCollection with features array
   - `GET /api/districts/` - districts array with geometry
   - `GET /api/trash-sites/<id>/detail/` - site with photos/proofs/permissions
   - `GET /api/cleanups/` - paginated results with count/page/num_pages
   - `GET /healthz` - ok + database status

Expected:
- All return 200 with documented JSON shapes.

## MT-020 Mobile Viewport
Related feature: `F-003`

Steps:
1. Open map at 375px width (or phone device emulation).
2. Test mode switching, report submission, and cleanup flow.
3. Verify modals are usable on small screens.

Expected:
- All interactions work on mobile viewport.
- Modals are scrollable and dismissible.
