# Upper-Cumberland CleanUp

Interactive web app for reporting trash and organizing cleanup efforts in the Upper Cumberland region of Tennessee, starting with Putnam County Commission District 3.

- Backend: Django + GeoDjango + PostGIS
- Frontend: Django templates + Leaflet + leaflet-draw + vanilla JS
- Auth: public map viewing; login required to submit reports/cleanups
- Anti-abuse: django-ratelimit + IP ban middleware

## Demo

### Report Mode — Site Detail with Area Polygon
![Report mode with area polygon and site detail](images/Demo_1.png)

### Completed Cleanups Page
![Public cleanups showcase](images/Demo_2.png)

### District 3 Boundary with Site Detail & Popup
![District 3 boundary with trash site detail and mark cleaned popup](images/Demo_3.png)

### Cleanup Mode — Draw Area
![Cleanup mode with draw area tool active](images/Demo_4.png)

## Core Features

### Two-Mode Map UI
- **Report Trash**: Place a pin or draw a polygon area, add description/severity/photos (max 5)
- **Cleanup Trash**: Click active reports, submit before/after photos and cleanup proof

### Public Pages
- `/` — Interactive map with Putnam County boundary and District 3 overlay
- `/cleanups/` — Public showcase of completed cleanups with before/after galleries
- `/accounts/login/` and `/accounts/signup/` — Authentication

### District Abstraction
- District boundaries stored in DB (not hardcoded)
- Putnam County boundary rendered as outer mask; District 3 shown as labeled inner boundary
- Trash sites auto-assigned to districts via spatial query
- Designed for future multi-district support

### Security
- Rate limiting on all API endpoints (django-ratelimit)
- IP ban table with optional expiry
- CSRF protection on all write endpoints
- Photo upload validation (count, size, MIME type)

## Tech Stack

- Python 3.12, Django 5.2.x
- PostgreSQL 16 + PostGIS 3.4
- Pillow, Gunicorn, WhiteNoise
- django-storages + boto3 for S3/R2 media
- django-ratelimit for API throttling
- Leaflet 1.9.4 + leaflet-draw 1.0.4
- CARTO Voyager basemap tiles

## Data Model

### `District`
- `id` UUID, `name`, `slug` (unique), `geometry` MultiPolygonField, `active` bool

### `TrashSite`
- `id` UUID, `status` (PENDING/IN_PROGRESS/CLEANED/INVALID)
- `location` PointField, `area` PolygonField (optional, for area reports)
- `district` FK(District), `title`, `description`, `severity`, `hazard_flag`
- `created_by`, `claimed_by`, `created_at`, `cleaned_at`

### `CleanupProof`
- `trash_site` FK, `note`, `bags_count`, `created_by`

### `Photo`
- `image` ImageField, `proof` FK, `photo_type` (REPORT/BEFORE/AFTER)

### `IPBan`
- `ip_address`, `reason`, `expires_at` (null = permanent)

## API Endpoints

### Public (no login)
- `GET /` — Map view
- `GET /cleanups/` — Cleanup showcase
- `GET /healthz` — Health check
- `GET /api/features/?bbox=&status=&days=&district=` — GeoJSON features
- `GET /api/districts/` — Active districts with geometry
- `GET /api/trash-sites/<id>/detail/` — Site detail
- `GET /api/cleanups/?page=&page_size=` — Paginated cleaned sites

### Authenticated
- `POST /api/trash-sites/` — Create report (multipart, max 5 photos)
- `PATCH /api/trash-sites/<id>/` — Update site
- `POST /api/trash-sites/<id>/mark-cleaned/` — Submit cleanup proof (before/after photos)
- `POST /api/feedback/` — Submit feedback

## Setup

### Docker (recommended)

```powershell
cd C:\Users\Brlan\Documents\Coding\concept\site\trash-proj\putnam_trashmap
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

App at `http://127.0.0.1:8000/`. Putnam County and District 3 boundaries are auto-seeded on startup.

### Environment Variables

See `.env.example`. Key variables:
- `REDIS_URL` — Optional Redis for rate limit cache (defaults to in-memory)

## Testing

```powershell
docker compose run --rm web python manage.py test
```

## Accessibility

- Skip-to-content link
- ARIA roles on all modals (`role="dialog"`, `aria-modal="true"`)
- Focus trap and return on modal open/close
- `aria-live` regions for toasts, detail panel, mode instructions
- WCAG 2.1 AA color contrast compliance
- Keyboard navigable map controls
- Responsive hamburger nav for mobile viewports
