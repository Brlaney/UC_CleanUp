# AGENTS.md

Project-specific guide for coding agents and contributors working on this repository.

## 1) Mission

Build and maintain a production-ready interactive CleanUp map for the **Upper Cumberland region of Tennessee** — currently Putnam County and all 12 Commission Districts — with two core modes: **Report Trash** and **Cleanup Trash**. The district layer is abstracted (`District` model + `/api/districts/`) so coverage can expand to more counties without code changes.

Key priorities:

- Public map viewing; login required to submit reports or cleanups.
- District geo-data abstracted — now all 12 Commission Districts; extensible to more counties.
- Anti-abuse: rate limiting + IP banning.
- Modern, accessible, mobile-first UI/UX.
- Preserve geospatial correctness (`SRID 4326`, `[lng, lat]` order).

## 2) Stack and Boundaries

- Django templates + vanilla JS frontend only.
- GeoDjango + PostGIS backend.
- No React/Next.js in this repo.
- Media files stored locally in development, S3/R2 in production.
- `django-ratelimit` for API throttling.
- Auth required for POST/PATCH endpoints only.

## 3) Ground Rules for Changes

1. Do not break existing API endpoint paths without updating frontend calls.
2. Do not change coordinate order from `[lng, lat]`.
3. Keep geometry fields as `geography=True`, `srid=4326`.
4. If models change, include migration files.
5. If API payloads change, update views, frontend JS, and docs.
6. Add or update tests for behavioral changes.
7. Keep auth protection on write endpoints (create, update, mark-cleaned, feedback).
8. Public read endpoints (features, districts, detail, cleanups) must remain unauthenticated.
9. Rate limits must be preserved on all API endpoints.

## 4) File Ownership Map

- `geoapp/models.py`: schema and geometry behavior (District, TrashSite, IPBan, etc.)
- `geoapp/views.py`: JSON API and template views
- `geoapp/urls.py`: route contracts
- `geoapp/validators.py`: upload validation
- `geoapp/middleware.py`: IP ban enforcement
- `geoapp/permissions.py`: role/permission checks
- `geoapp/services.py`: activity logging, district assignment
- `templates/geoapp/map.html`: two-mode map UI
- `templates/geoapp/cleanups.html`: public cleanup showcase
- `static/js/map.js`: map interactions and AJAX
- `static/js/utils.js`: shared utilities (toast, modal, CSRF, fetch)
- `static/js/base.js`: feedback modal
- `static/css/palette.css`: design tokens
- `geoapp/tests.py`: critical behavior validation
- `docker-compose.yml`, `Dockerfile`: local runtime

## 5) API/Frontend Consistency Checklist

When adding or renaming fields, update all of:

1. Model field definition
2. Serializer output in views
3. Endpoint input parsing/validation
4. Frontend form controls
5. Frontend fetch payload construction
6. Detail/popup rendering
7. Tests
8. README endpoint docs

## 6) Common Pitfalls

- Using `[lat, lng]` accidentally in stored data.
- Forgetting CSRF header on POST/PATCH requests.
- Adding model fields without migration.
- Breaking the two-mode UI state management in map.js.
- Not validating photo uploads server-side.
- Forgetting to update rate limit decorators on new endpoints.

## 7) Testing Expectations

- `python manage.py test` passes in container.
- Existing tests still pass after changes.
- New logic includes at least one targeted test.
- Rate limit tests use `@override_settings(RATELIMIT_ENABLE=False)` when not testing limits.

## 8) Documentation Policy

Any of the following requires README update:
- New env vars
- Endpoint path or payload changes
- Setup workflow changes
- Docker behavior changes
- Auth or permission model changes
