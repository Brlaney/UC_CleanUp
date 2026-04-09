# Upper-Cumberland CleanUp

Interactive web map for reporting trash and organizing cleanup efforts in the Upper Cumberland region of Tennessee — starting with Putnam County Commission District 3.

**Live:** [uc-cleanup.com](https://uc-cleanup.com)

---

## Features

| | |
|---|---|
| **Report Trash** | Place a pin or draw a polygon, add description, severity, and up to 5 photos |
| **Cleanup Trash** | Claim an active report, submit before/after photos and proof |
| **Public Map** | Putnam County boundary + District 3 overlay, real-time marker filtering |
| **Cleanups Page** | Public gallery of completed cleanups with photo proof |
| **Mobile-first** | Responsive bottom sheet panel, touch-friendly controls |

## Screenshots

<table>
<tr>
<td><img src="images/Demo_1.png" alt="Report mode with site detail" width="420"></td>
<td><img src="images/Demo_2.png" alt="Completed cleanups page" width="420"></td>
</tr>
<tr>
<td><img src="images/Demo_3.png" alt="District 3 boundary with site detail" width="420"></td>
<td><img src="images/Demo_4.png" alt="Cleanup mode draw area" width="420"></td>
</tr>
</table>

## Tech Stack

- **Backend:** Python 3.12, Django 5.2, GeoDjango, PostGIS 3.4
- **Frontend:** Django templates, Leaflet 1.9.4, leaflet-draw, vanilla JS
- **Database:** PostgreSQL 16 + PostGIS (Supabase in production)
- **Storage:** Cloudflare R2 via django-storages + boto3
- **Serving:** Gunicorn + WhiteNoise, deployed on Render
- **Auth:** django.contrib.auth — public read, login required to write
- **Anti-abuse:** django-ratelimit + IP ban middleware

## Local Development

### Prerequisites

- Docker + Docker Compose

### Run

```bash
git clone https://github.com/Brlaney/Upper-Cumberland-CleanUp.git
cd Upper-Cumberland-CleanUp
docker compose up --build
```

App is at `http://localhost:8000`. Putnam County and District 3 boundaries are seeded automatically on first run.

```bash
# Create a superuser
docker compose exec web python manage.py createsuperuser
```

### Environment Variables

Copy `.env.example` to `.env` and fill in values. Key variables:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `1` for local dev, `0` for production |
| `DB_CONN_STRING` | Full PostgreSQL connection string (production) |
| `CF_ACCESS_KEY_ID` | Cloudflare R2 access key |
| `CF_SECRET_ACCESS_KEY` | Cloudflare R2 secret |
| `CF_BUCKET_NAME` | R2 bucket name |
| `CF_S3_ENDPOINT_URL` | R2 endpoint URL |
| `CF_S3_CUSTOM_DOMAIN` | R2 public domain for media URLs |
| `USE_S3_MEDIA` | `1` to use R2 for media, `0` for local |

## API Endpoints

### Public

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Map view |
| `GET` | `/cleanups/` | Completed cleanups gallery |
| `GET` | `/about/` | About page |
| `GET` | `/api/features/` | GeoJSON features (`bbox`, `status`, `days`, `district`) |
| `GET` | `/api/districts/` | Active district boundaries |
| `GET` | `/api/trash-sites/<id>/detail/` | Site detail |
| `GET` | `/api/cleanups/` | Paginated cleaned sites |
| `GET` | `/healthz` | Health check |

### Authenticated

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/trash-sites/` | Create trash report (multipart, max 5 photos) |
| `PATCH` | `/api/trash-sites/<id>/` | Update site |
| `POST` | `/api/trash-sites/<id>/mark-cleaned/` | Submit cleanup proof |
| `POST` | `/api/feedback/` | Submit feedback |

## Data Model

```
District        — name, slug, geometry (MultiPolygon), active
TrashSite       — status, location (Point), area (Polygon), district FK,
                  title, description, severity, hazard_flag,
                  created_by, claimed_by, created_at, cleaned_at
CleanupProof    — trash_site FK, note, bags_count, created_by
Photo           — image, proof FK, photo_type (REPORT/BEFORE/AFTER)
IPBan           — ip_address, reason, expires_at
```

## Security

- Rate limiting on all API endpoints (django-ratelimit)
- IP ban table with optional expiry
- CSRF protection on all write endpoints
- Photo upload validation (count, size, MIME type)
- `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` in production

## License

MIT
