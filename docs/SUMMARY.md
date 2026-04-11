# UC CleanUp — Project Summary

A community-driven litter tracking and cleanup coordination app for the **Upper Cumberland region of Tennessee**, covering all 12 Putnam County Commission Districts. Built with Django 5 + GeoDjango (PostGIS), Leaflet.js, and vanilla JS. The map is publicly viewable; an account is required only to submit reports, log cleanups, or RSVP to events.

---

## Pages

| Route | Access | Purpose |
|---|---|---|
| `/` | Public | Interactive Leaflet map |
| `/cleanups/` | Public | Gallery of completed cleanup sites |
| `/leaderboard/` | Public | Volunteer leaderboard (monthly / all-time) |
| `/events/` | Public | Community cleanup event listing |
| `/teams/` | Public | Civic group / team listing |
| `/teams/<slug>/` | Public | Team detail page with aggregate stats |
| `/teams/<slug>/certificate/` | Public | Printable team contribution certificate |
| `/share/<site-id>/` | Public | OpenGraph share page for a cleaned site |
| `/about/` | Public | Project information |
| `/profile/` | Auth required | User contribution stats and preferences |
| `/accounts/login/` | Public | Login |
| `/accounts/signup/` | Public | Registration |
| `/accounts/forgot-username/` | Public | Recover username via email |
| `/accounts/password_reset/` | Public | Reset password via email |

---

## What Users Can Do

### Report a Trash Site
Authenticated users switch to **Report mode** on the map and either drop a pin (point) or draw a polygon (area). A modal collects an optional title, description, severity (Light / Medium / Heavy), a hazard flag, an optional team association, and up to 5 photos. On submit the site is created via `POST /api/trash-sites/`, the district is auto-assigned by a PostGIS spatial query, and `notify_nearby_subscribers()` fires push notifications to users within their saved radius.

If the device is **offline**, the report is saved to IndexedDB and synced automatically when connectivity returns (Background Sync via service worker).

### Mark a Site as Cleaned
In **Cleanup mode**, clicking any active marker opens its detail panel. Authenticated users can tap "Mark Cleaned" to submit before photos, after photos, a bag count, notes, and an optional team association. This creates a `CleanupProof` record, sets the site status to `CLEANED`, and records `cleaned_at` via `POST /api/trash-sites/<id>/mark-cleaned/`.

### Verify a Cleanup (Coordinator / Admin)
Users with the **Coordinator** or **Admin** role see a "Verify Cleanup" button on any CLEANED site. Clicking it records `verified_by`, `verified_at`, an optional verification note, and a work order number via `POST /api/trash-sites/<id>/verify/`. A "Verified ✓" badge appears in the detail panel.

### Community Impact Counter
A live stats bar at the top of the map control panel shows **bags collected**, **sites cleaned**, **sites reported**, and **active volunteers this month** — fetched from `GET /api/impact/` (5-minute server-side cache). Numbers animate in with a cubic ease-out rollup on page load.

### Hotspot Heatmap
A Leaflet.heat overlay visualises trash density by severity (Light = 0.3, Medium = 0.6, Heavy = 1.0). Toggled via a checkbox in the Layers panel. Fetched once from `GET /api/heatmap/`.

### Share a Cleaned Site
Any detail panel has a "Share" button. On supporting devices this triggers the native Web Share API. As a fallback a modal provides Copy Link, Facebook sharer, and X/Twitter intent links. Each cleaned site has a dedicated `/share/<id>/` page with full OpenGraph + Twitter Card meta tags for rich link previews.

### Browse Completed Cleanups
The public `/cleanups/` page lists every cleaned site with before/after photo galleries, bag counts, and who reported the site. Backed by `GET /api/cleanups/`.

### Volunteer Leaderboard
`/leaderboard/` ranks the top 10 volunteers by cleanup count for the current month or all time. Users opt in to showing their username publicly via a toggle on `/profile/`; otherwise they appear as "Anonymous". Backed by `GET /api/leaderboard/?period=month|alltime`.

### Cleanup Events
Any authenticated user can create a cleanup event by clicking "Create Event" in the report panel, then clicking the map to set the location. Events appear as calendar markers on the map. Clicking one opens an event detail card showing date, organizer, RSVP count, and an RSVP / Cancel RSVP button.

- `POST /api/events/` — create event
- `POST /api/events/<id>/rsvp/` — RSVP (sends confirmation email)
- `DELETE /api/events/<id>/rsvp/` — cancel RSVP
- `POST /api/events/<id>/complete/` — mark completed (organizer / admin)
- `GET /events/` — public listing with Upcoming / Past tab switcher

A management command `send_event_reminders` runs daily and emails all RSVP'd attendees 18–30 hours before the event.

### Teams
Civic groups, schools, scout troops, and churches can create a team at `/teams/`. Team pages show aggregate stats (members, sites reported, cleanups, bags collected) and a printable certificate. Members can optionally associate a report or cleanup with their team via a selector in the map forms.

- `GET /api/teams/` — list all teams
- `POST /api/teams/` — create team (auth)
- `GET /api/teams/<slug>/` — team stats
- `POST /api/teams/<slug>/join/` — join team (auth)

### Monthly Problem-Site Report
A management command `send_monthly_report` runs on the 1st of each month, queries all sites that have been PENDING or IN_PROGRESS for 90+ days, and emails a formatted table to the district rep address (`DISTRICT_REP_EMAIL` env var).

### Offline Support (PWA)
The app registers a service worker at `/sw.js` and ships a Web App Manifest, making it installable to the home screen on Android and iOS. The service worker:
- Caches the app shell on install (HTML, CSS, JS)
- Serves static assets cache-first; falls back to network
- Queues trash reports submitted while offline in IndexedDB; flushes them automatically on reconnect
- Shows an amber offline banner when `navigator.onLine` is false

### Push Notifications
Users can click "Enable Notifications" in the report panel to subscribe to browser push alerts for new trash reports near their current map view. Backed by VAPID (`pywebpush`). New reports trigger `notify_nearby_subscribers()` which queries `PushSubscription` records by `saved_location__dwithin` and dispatches push payloads to matching subscribers.

### Map Settings / Layer Preferences
The Settings gear opens a modal where authenticated users choose which commission district boundaries are displayed and set a default county. Preferences are saved via `POST /api/preferences/` and applied on next map load, including zooming to the saved district bounds.

### User Profile and Contribution Stats
`/profile/` shows reports submitted, cleanups logged, and a toggle for leaderboard opt-in. The profile also links to the leaderboard.

### Submit In-App Feedback
Authenticated users can submit a bug report, feature request, or general comment from the top nav. Stored as `FeedbackEntry` records, reviewed via Django admin.

### Account Recovery
- **Forgot password** — `/accounts/password_reset/` uses Django's built-in `PasswordResetView`.
- **Forgot username** — `/accounts/forgot-username/` accepts an email and sends the associated username(s). Always shows the confirmation page to prevent account enumeration.

---

## How the Models Fit Together

```
User
 ├── Profile              (role: MEMBER / COORDINATOR / ADMIN, public_profile)
 ├── UserMapPreference    (saved district/county display prefs)
 ├── TrashSite [created_by → SET_NULL]
 │    ├── area            (optional polygon, SRID 4326)
 │    ├── district FK → District
 │    ├── team FK → Team
 │    ├── verified_by FK → User
 │    └── CleanupProof [created_by → SET_NULL]
 │         ├── team FK → Team
 │         └── Photo (photo_type: REPORT / BEFORE / AFTER)
 ├── CleanupEvent [organizer → SET_NULL]
 │    └── EventRSVP [user → SET_NULL]
 ├── TeamMembership → Team
 ├── PushSubscription     (endpoint, p256dh, auth_key, saved_location Point)
 ├── ActivityLog [actor → SET_NULL]
 └── FeedbackEntry [created_by → SET_NULL]

District
 └── geometry MultiPolygonField (SRID 4326, spatial_index)

Team
 ├── leader FK → User
 ├── district FK → District
 └── TeamMembership (role: LEADER / MEMBER)
```

All `created_by` / `actor` foreign keys use `SET_NULL` on user deletion, preserving reports and cleanup history when an account is removed.

---

## API Endpoints

### Public
| Method | Path | Description |
|---|---|---|
| GET | `/api/features/` | GeoJSON FeatureCollection (bbox, status, days, district filters) |
| GET | `/api/districts/` | Active district geometries |
| GET | `/api/impact/` | Aggregate impact stats (5-min cache) |
| GET | `/api/heatmap/` | Trash density heat points |
| GET | `/api/leaderboard/` | Top 10 volunteers (`period=month\|alltime`) |
| GET | `/api/events/` | Paginated event list |
| GET | `/api/events/<id>/` | Event detail |
| GET | `/api/teams/` | All teams with stats |
| GET | `/api/teams/<slug>/` | Single team detail |
| GET | `/api/trash-sites/<id>/detail/` | Full site detail with photos and proof history |
| GET | `/api/cleanups/` | Paginated cleaned sites |
| GET | `/api/push/vapid-key/` | VAPID public key |
| GET | `/healthz` | Database connectivity check |

### Authenticated
| Method | Path | Description |
|---|---|---|
| POST | `/api/trash-sites/` | Create trash site (point or polygon, multipart) |
| PATCH | `/api/trash-sites/<id>/` | Update status, title, description, severity, hazard |
| POST | `/api/trash-sites/<id>/mark-cleaned/` | Submit cleanup proof |
| POST | `/api/trash-sites/<id>/verify/` | Verify cleanup (Coordinator / Admin only) |
| POST | `/api/events/` | Create cleanup event |
| POST | `/api/events/<id>/rsvp/` | RSVP to event |
| DELETE | `/api/events/<id>/rsvp/` | Cancel RSVP |
| POST | `/api/events/<id>/complete/` | Mark event completed (organizer / admin) |
| POST | `/api/teams/` | Create team |
| POST | `/api/teams/<slug>/join/` | Join team |
| POST | `/api/push/subscribe/` | Subscribe to push notifications |
| POST | `/api/push/unsubscribe/` | Unsubscribe from push notifications |
| GET/POST | `/api/preferences/` | Read or save map display preferences |
| POST | `/api/feedback/` | Submit in-app feedback |

---

## Security

- **Rate limiting** via `django-ratelimit`: per-IP on read endpoints, per-user on write endpoints. Backed by in-memory cache (or Redis if `REDIS_URL` is set).
- **IP banning** via `IPBanMiddleware`: checks every request against the `IPBan` table; supports permanent and time-limited bans.
- **Role system**: `MEMBER` → `COORDINATOR` (can verify cleanups) → `ADMIN` (full access, can invalidate sites).
- **Photo upload validation**: max 5 files, 10 MB each, image MIME types only (JPEG, PNG, WebP, HEIC).
- **Permission checks**: only the site creator or admin can edit a trash site; only Coordinator/Admin can verify; only admins can mark `INVALID`.
- **CSRF protection** on all write endpoints.

---

## Infrastructure

- **Database**: PostgreSQL 16 + PostGIS 3.4. SRID 4326 throughout; `geography=True` for accurate distance calculations.
- **File storage**: local filesystem in dev; Cloudflare R2 (S3-compatible) in production via `django-storages`.
- **Email**: console backend in dev; SMTP via env vars in production. Used for RSVP confirmations, event reminders, monthly reports, and account recovery.
- **Push notifications**: `pywebpush` + VAPID key pair. Set `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_EMAIL` in env.
- **Scheduled commands**:
  - `send_event_reminders` — daily, emails attendees 18–30h before each event
  - `send_monthly_report` — 1st of month, emails chronic problem sites to district rep
- **PWA**: service worker at `/sw.js` (Django view with `Service-Worker-Allowed: /`), `static/manifest.json`.
- **Deployment**: Dockerized with `web-entrypoint.sh` (migrate → seed districts → collect static → start Gunicorn). Hosted on Render.
- **Settings fix**: `dj_database_url.parse()` instead of `.config()` so `DATABASE_URL=""` in docker-compose falls through to the `POSTGRES_*` variable fallback correctly.
