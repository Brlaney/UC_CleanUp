# UC CleanUp — Project Summary

A community-driven litter tracking and cleanup coordination app focused on **Putnam County Commission District 3**. Built with Django 5 + GeoDjango (PostGIS), Leaflet.js, and vanilla JS. The map is publicly viewable; an account is required only to submit reports or log cleanups.

---

## Pages

| Route | Access | Purpose |
|---|---|---|
| `/` | Public | Interactive Leaflet map |
| `/cleanups/` | Public | Gallery of completed cleanup sites |
| `/about/` | Public | Project information |
| `/profile/` | Auth required | User contribution stats |
| `/accounts/login/` | Public | Login |
| `/accounts/signup/` | Public | Registration |
| `/accounts/forgot-username/` | Public | Recover username via email |
| `/accounts/password_reset/` | Public | Reset password via email |

---

## What Users Can Do

### Report a Trash Site
Authenticated users switch to **Report mode** on the map and either drop a pin (point) or draw a polygon (area). A modal collects an optional title, description, severity level (Light / Medium / Heavy), a hazard flag, and up to 5 photos. On submit, the site is created via `POST /api/trash-sites/`, the district is auto-assigned by a PostGIS spatial query, and a marker appears on the map immediately.

### Mark a Site as Cleaned
In **Cleanup mode**, clicking any active marker opens its detail panel. Authenticated users can tap "Mark Cleaned" to open a cleanup modal where they submit before photos, after photos, a bag count, and notes. This creates a `CleanupProof` record, updates the site's status to `CLEANED`, and records a `cleaned_at` timestamp via `POST /api/trash-sites/<id>/mark-cleaned/`.

### Browse Completed Cleanups
The public `/cleanups/` page lists every site that has been marked cleaned, with before/after photo galleries, bag counts, and who reported the site. Backed by a paginated `GET /api/cleanups/` endpoint.

### View Trash Site Details
Clicking any marker on the map loads full detail from `GET /api/trash-sites/<id>/detail/` — status badge, severity, hazard flag, description, and all attached photos grouped by type (report / before / after), plus a full proof history showing each cleanup submission.

### Filter the Map
The cleanup mode panel exposes status filter chips (Pending / In Progress / Cleaned). Markers reload automatically as the map is panned or zoomed using `GET /api/features/?bbox=&status=&district=`.

### User Profile and Contribution Stats
Authenticated users can view `/profile/` to see how many trash sites they have reported and how many cleanups they have submitted, plus their member-since date. The username in the top nav links directly to this page. Counts are computed from `TrashSite.created_by` and `CleanupProof.created_by` queries.

### Map Settings / Layer Preferences
The Settings gear in the nav bar opens a modal where authenticated users can choose which commission district boundaries are displayed and set a default county. Preferences are saved server-side via `POST /api/preferences/` and applied automatically on next map load, including zooming the map to the saved district boundary.

### Submit In-App Feedback
Authenticated users can open a feedback modal from the top nav to submit a bug report, feature request, or general comment. Submissions are stored as `FeedbackEntry` records and reviewed through the Django admin.

### Account Recovery
- **Forgot password** — `/accounts/password_reset/` uses Django's built-in `PasswordResetView`. The user enters their email and receives a one-time reset link.
- **Forgot username** — `/accounts/forgot-username/` accepts an email address and sends the associated username(s) via email. The confirmation page is always shown regardless of whether the email matched, preventing account enumeration.

---

## How the Core Models Fit Together

```
User
 ├── Profile          (role: MEMBER / ADMIN)
 ├── UserMapPreference (saved district/county display prefs)
 ├── TrashSite [created_by → SET_NULL on user delete]
 │    ├── area        (optional polygon, SRID 4326)
 │    ├── district FK → District
 │    └── CleanupProof [created_by → SET_NULL]
 │         └── Photo (photo_type: REPORT / BEFORE / AFTER)
 ├── ActivityLog [actor → SET_NULL]
 └── FeedbackEntry [created_by → SET_NULL]

District
 └── geometry MultiPolygonField (SRID 4326, spatial_index)
```

All `created_by` / `actor` foreign keys use `SET_NULL` on user deletion, so trash reports, cleanup proofs, and activity history are preserved even if the submitting account is removed.

---

## API Endpoints

### Public
| Method | Path | Description |
|---|---|---|
| GET | `/api/features/` | GeoJSON FeatureCollection of trash sites (bbox, status, days, district filters) |
| GET | `/api/districts/` | Active district geometries as GeoJSON |
| GET | `/api/trash-sites/<id>/detail/` | Full detail for one trash site including grouped photos and proof history |
| GET | `/api/cleanups/` | Paginated list of cleaned sites with photos |
| GET | `/healthz` | Database connectivity check |

### Authenticated
| Method | Path | Description |
|---|---|---|
| POST | `/api/trash-sites/` | Create a trash site (point or polygon) |
| PATCH | `/api/trash-sites/<id>/` | Update status, title, description, severity, hazard flag |
| POST | `/api/trash-sites/<id>/mark-cleaned/` | Submit cleanup proof with before/after photos |
| GET/POST | `/api/preferences/` | Read or save map display preferences |
| POST | `/api/feedback/` | Submit in-app feedback |

---

## Security

- **Rate limiting** via `django-ratelimit`: per-IP on read endpoints, per-user on write endpoints. Backed by in-memory cache (or Redis if `REDIS_URL` is set).
- **IP banning** via `IPBanMiddleware`: checks every request against the `IPBan` table. Supports permanent and time-limited bans.
- **Photo upload validation**: max 5 files, 10 MB each, image MIME types only (JPEG, PNG, WebP, HEIC).
- **Permission checks**: only the site creator or an admin can edit a trash site; only admins can mark a site `INVALID`.

---

## Infrastructure

- **Database**: PostgreSQL 16 with PostGIS 3.4 extension.
- **Geometry**: SRID 4326 throughout; `geography=True` for accurate distance calculations.
- **File storage**: local filesystem in dev; Cloudflare R2 (S3-compatible) in production via `django-storages`.
- **Deployment**: Dockerized with a `web-entrypoint.sh` that runs migrations, seeds district data, and starts Gunicorn. Hosted on Render.
