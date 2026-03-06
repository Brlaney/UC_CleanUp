# Upper Cumberland CleanUp Map (Django + GeoDjango)

All-Django web app for tracking trash sites and cleanup routes in Putnam County, TN.

- Backend: Django + GeoDjango + PostGIS
- Frontend: Django templates + Leaflet + leaflet-draw + vanilla JS
- Auth: login required for all map and API access (invite-only via admin user creation)

## 1) Current MVP Capabilities

- Add `TrashSite` point pins with default status `PENDING`.
- View shared trash pins and cleanup routes on a common map.
- Mark a trash site as `CLEANED` with:
  - note
  - bags count
  - one or more photos
- Draw and save `RouteCleanup` polylines with:
  - notes
  - optional time spent
  - optional photos
  - server-computed `distance_miles`
- Filter map features by:
  - trash status (`PENDING`, `IN_PROGRESS`, `CLEANED`)
  - date range (`7`, `30`, `all`)
- Manage all records through Django admin.

## 2) Tech Stack

- Python 3.12
- Django 5.2.x
- PostgreSQL 16 + PostGIS 3.4
- Pillow for image uploads
- Leaflet + leaflet-draw via CDN

## 3) Project Layout

```text
putnam_trashmap/
  manage.py
  requirements.txt
  Dockerfile
  docker-compose.yml
  .env.example
  .dockerignore
  README.md
  AGENTS.md
  docker/
    web-entrypoint.sh
  putnam_trashmap/
    settings.py
    urls.py
  geoapp/
    admin.py
    models.py
    urls.py
    views.py
    tests.py
    migrations/
  templates/
    base.html
    geoapp/map.html
    registration/login.html
  static/
    css/site.css
    css/map.css
    js/map.js
```

## Documentation

- [Feature inventory (as-is)](docs/FEATURES.md)
- [QA coverage matrix](docs/QA_MATRIX.md)
- [Manual test scripts](docs/MANUAL_TESTS.md)
- [UI roadmap (future only)](docs/UI_ROADMAP.md)

## Theme Palette

Edit all app theme and map colors in one place:

- `static/css/palette.css`

This file controls:

- top bar and button colors
- panel/surface/border colors
- modal overlay color
- map marker status colors
- route and draw-line colors

## 4) Data Model

### `TrashSite`

- `id` UUID (PK)
- `status`: `PENDING | IN_PROGRESS | CLEANED | INVALID`
- `location`: `PointField(geography=True, srid=4326)`
- `title`, `description` optional
- `severity`: `LIGHT | MEDIUM | HEAVY` optional
- `hazard_flag`: bool
- `created_by` (required), `claimed_by` (optional)
- `created_at`, `updated_at`, `cleaned_at`

### `RouteCleanup`

- `id` UUID (PK)
- `geometry`: `LineStringField(geography=True, srid=4326)`
- `status`: `LOGGED | VERIFIED`
- `notes` optional
- `distance_miles` float (computed server-side on save)
- `time_spent_minutes` optional
- `created_by`, `created_at`

### `CleanupProof`

- `id` UUID (PK)
- Links to `trash_site` or `route_cleanup` (at least one expected)
- `note`, `bags_count`
- `created_by`, `created_at`

### `Photo`

- `id` UUID (PK)
- `image` (`ImageField`)
- `proof` FK
- `created_at`

## 5) Geometry and Distance Rules

- Coordinate order is always `[lng, lat]`.
- Spatial fields use SRID 4326 and `geography=True`.
- Route distance is computed in model `save()`:
  - geodesic segment sum in meters (Haversine)
  - converted with `miles = meters * 0.000621371`

## 6) API Endpoints

All endpoints require login.

### HTML Routes

- `GET /` -> redirects to `/map/`
- `GET /accounts/login/` -> Django auth login
- `GET /map/` -> main map UI
- `GET /admin/` -> Django admin

### JSON Routes

- `GET /api/features/?bbox=minLng,minLat,maxLng,maxLat&status=PENDING,CLEANED&days=7`
- `POST /api/trash-sites/`
- `GET /api/trash-sites/<id>/`
- `PATCH /api/trash-sites/<id>/`
- `POST /api/trash-sites/<id>/mark-cleaned/`
- `GET /api/trash-sites/<id>/detail/`
- `POST /api/route-cleanups/`
- `GET /api/route-cleanups/<id>/`
- `GET /api/route-cleanups/<id>/detail/`

### Request Examples

Create trash site (multipart):

```bash
curl -X POST http://127.0.0.1:8001/api/trash-sites/ \
  -H "X-CSRFToken: <csrftoken>" \
  -b "sessionid=<session>; csrftoken=<csrftoken>" \
  -F "lat=36.1627" \
  -F "lng=-85.5016" \
  -F "title=Roadside litter" \
  -F "description=Near greenway entrance" \
  -F "severity=MEDIUM" \
  -F "hazard_flag=true" \
  -F "photos=@cleanup1.jpg"
```

Mark cleaned (multipart):

```bash
curl -X POST http://127.0.0.1:8001/api/trash-sites/<id>/mark-cleaned/ \
  -H "X-CSRFToken: <csrftoken>" \
  -b "sessionid=<session>; csrftoken=<csrftoken>" \
  -F "note=Cleared area and bagged trash" \
  -F "bags_count=3" \
  -F "photos=@after.jpg"
```

Create route cleanup (JSON):

```bash
curl -X POST http://127.0.0.1:8001/api/route-cleanups/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: <csrftoken>" \
  -b "sessionid=<session>; csrftoken=<csrftoken>" \
  -d '{
    "coordinates": [[-85.50, 36.16], [-85.49, 36.161], [-85.485, 36.162]],
    "notes": "Shoulder cleanup",
    "time_spent_minutes": 45
  }'
```

## 7) Environment Variables

See `.env.example`.

- `SECRET_KEY`
- `DEBUG` (`1` or `0`)
- `ALLOWED_HOSTS` (comma-separated)
- `TIME_ZONE`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `WEB_PORT` (host port mapped to container 8000)
- `INVITE_CODE` (reserved; signup not currently enabled)

## 8) Setup and Run

### Option A: Recommended (Full Docker)

This avoids local GDAL setup.

1. Start app stack:

```powershell
cd C:\Users\Brlan\Documents\Coding\concept\site\trash-proj\putnam_trashmap
docker compose up --build -d
```

2. If host port 8000 is occupied, use another port:

```powershell
$env:WEB_PORT="8001"
docker compose up --build -d
```

3. Create an admin user:

```powershell
docker compose exec web python manage.py createsuperuser
```

4. Open app:

- `http://127.0.0.1:8000/map/` (or `8001` if `WEB_PORT=8001`)
- `http://127.0.0.1:8000/accounts/login/`
- `http://127.0.0.1:8000/admin/`

5. Useful commands:

```powershell
docker compose logs -f web
docker compose exec web python manage.py test
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose down
```

### Option B: Local Python + Docker DB

Use this only if you need to run Django outside containers.

1. Start DB only:

```powershell
docker compose up -d db
```

2. Create venv and install:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Export environment variables (`POSTGRES_HOST=127.0.0.1`):

```powershell
$env:SECRET_KEY="dev-secret-change-me"
$env:DEBUG="1"
$env:ALLOWED_HOSTS="127.0.0.1,localhost"
$env:TIME_ZONE="America/Chicago"
$env:POSTGRES_DB="putnam_trashmap"
$env:POSTGRES_USER="putnam"
$env:POSTGRES_PASSWORD="putnam"
$env:POSTGRES_HOST="127.0.0.1"
$env:POSTGRES_PORT="5432"
```

4. Run:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## 9) Windows GDAL Setup (Local Python Mode Only)

If you run Django locally and get `Could not find the GDAL library`:

1. Install OSGeo4W and include `gdal`, `geos`, `proj`.
2. Set env vars (adjust GDAL DLL version name):

```powershell
$env:OSGEO4W_ROOT="C:\OSGeo4W"
$env:PATH="$env:OSGEO4W_ROOT\bin;$env:PATH"
$env:GDAL_DATA="$env:OSGEO4W_ROOT\share\gdal"
$env:PROJ_LIB="$env:OSGEO4W_ROOT\share\proj"
$env:GDAL_LIBRARY_PATH="$env:OSGEO4W_ROOT\bin\gdal311.dll"
$env:GEOS_LIBRARY_PATH="$env:OSGEO4W_ROOT\bin\geos_c.dll"
```

3. Validate:

```powershell
python -c "from django.contrib.gis import geos; print(geos.GEOSGeometry('POINT (0 0)'))"
```

## 10) Testing

Current tests cover:

- `RouteCleanup.distance_miles` computation
- `mark-cleaned` behavior (`status=CLEANED`, `cleaned_at` set, proof created)

Run tests:

```powershell
docker compose exec web python manage.py test
```

## Smoke checks

Backend + unit/API smoke:

```powershell
python -m compileall geoapp putnam_trashmap
docker compose exec web python manage.py test
```

UI smoke (Playwright):

```powershell
npm install
npx playwright install chromium
npm run e2e:smoke
```

If your app is not on port 8000, set base URL (example 8001):

```powershell
$env:E2E_BASE_URL="http://127.0.0.1:8001"
npm run e2e:smoke
```

## 11) Enhancement Workflow

Recommended branch-based process:

1. Create a feature branch:

```powershell
git checkout -b feat/<short-feature-name>
```

2. Implement change in small slices:

- Models and migration
- API endpoint behavior
- Frontend map behavior
- Tests
- Docs

3. Run verification:

```powershell
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
```

4. Manual smoke check:

- login works
- map loads and fetches features
- create trash site
- mark cleaned with photo
- draw and save route

5. Commit:

```powershell
git add .
git commit -m "feat: <summary>"
```

## 12) Common Change Recipes

### Add a new field to `TrashSite`

1. Edit `geoapp/models.py`.
2. `docker compose exec web python manage.py makemigrations geoapp`
3. `docker compose exec web python manage.py migrate`
4. Update serializers in `geoapp/views.py`.
5. Update map UI/forms in `templates/geoapp/map.html` and `static/js/map.js`.
6. Add/adjust tests.

### Add a new filter to map

1. Add UI control in `templates/geoapp/map.html`.
2. Pass filter in `static/js/map.js` when calling `/api/features/`.
3. Apply filter logic in `geoapp/views.py` `features_api`.
4. Smoke test with different map extents and dates.

### Add a new photo-backed workflow

1. Use multipart form requests.
2. Read files via `request.FILES.getlist("photos")`.
3. Attach photos through `CleanupProof` + `Photo`.
4. Return media URLs in detail serializers.

## 13) Troubleshooting

### Docker builds but web container fails to bind port

- Error: `bind: Only one usage of each socket address...`
- Fix: set another host port:

```powershell
$env:WEB_PORT="8001"
docker compose up -d
```

### Docker Desktop stuck in "starting"

- Check:

```powershell
docker desktop status
```

- If `wslUpdateRequired=true`, run elevated:

```powershell
wsl --update
wsl --shutdown
docker desktop restart
```

### 403 CSRF on API POST/PATCH

- Ensure browser is logged in.
- Include CSRF token header and same-origin credentials in fetch requests.

### GDAL import errors in local Python

- Use Docker mode, or complete OSGeo4W setup in section 9.

### pytest runner expectations

- No automated test runner configured (pytest).
- Use Django's built-in runner: `python manage.py test`.

## 14) Security and Access

- No public signup in current MVP.
- Admin creates users in Django admin.
- All map/API endpoints require authenticated session.
- Media files are served directly by Django only in `DEBUG=1`.

## 15) Next Logical Improvements

- Activity timeline feed
- Better ownership/permission rules
- Per-user contribution analytics
- GPX import pipeline
- S3/R2 media storage for production
- Pagination and clustering at larger scale

## 16) GitHub Repo Setup

This project is now ready to publish with:

- `.gitignore` for Python/Django/Node local artifacts
- `.env.example` template (without secrets)
- GitHub Actions workflow at `.github/workflows/ci.yml` to run migrations + tests

Initial publish commands:

```powershell
cd C:\Users\Brlan\Documents\Coding\concept\site\trash-proj\putnam_trashmap
git init -b main
git add .
git commit -m "chore: initial project import"
git remote add origin https://github.com/<your-org-or-user>/<your-repo>.git
git push -u origin main
```

If a remote already exists:

```powershell
git remote set-url origin https://github.com/<your-org-or-user>/<your-repo>.git
git push -u origin main
```

If you ever staged generated files before `.gitignore` was added, untrack them:

```powershell
git rm -r --cached node_modules __pycache__ test-results playwright-report blob-report
git commit -m "chore: remove generated files from git tracking"
```
