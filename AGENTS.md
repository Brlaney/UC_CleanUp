# AGENTS.md

Project-specific guide for coding agents and contributors working on this repository.

## 1) Mission

Maintain and evolve the Upper Cumberland CleanUp Map MVP with minimal regressions.

Key priorities:

- Keep the app fully functional for logged-in users.
- Preserve geospatial correctness (`SRID 4326`, `[lng, lat]` order).
- Keep changes small, testable, and documented.

## 2) Stack and Boundaries

- Django templates + vanilla JS frontend only.
- GeoDjango + PostGIS backend.
- No React/Next.js in this repo.
- Media files stored locally in development.
- Auth required for all map/API routes.

## 3) Ground Rules for Changes

1. Do not break existing API endpoint paths without updating frontend calls.
2. Do not change coordinate order from `[lng, lat]`.
3. Keep geometry fields as `geography=True`, `srid=4326`.
4. If models change, include migration files.
5. If API payloads change, update:
   - `geoapp/views.py`
   - frontend JS usage in `static/js/map.js`
   - docs in `README.md`
6. Add or update tests for behavioral changes.
7. Keep auth protection on map and API routes.

## 4) Workflow for Feature Work

1. Create branch:

```powershell
git checkout -b feat/<short-name>
```

2. Implement in this sequence:

- data model
- migration
- API logic
- frontend integration
- tests
- docs

3. Verify in Docker:

```powershell
docker compose up -d
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
```

4. Manual smoke test:

- Login works.
- `/map/` loads.
- Add trash pin.
- Mark cleaned with proof.
- Draw and save route.
- Filter by status/date.

## 5) File Ownership Map (Practical)

- `geoapp/models.py`: schema and geometry behavior
- `geoapp/views.py`: JSON API and serialization
- `geoapp/urls.py`: route contracts
- `templates/geoapp/map.html`: map controls/modals layout
- `static/js/map.js`: map interactions and AJAX calls
- `geoapp/tests.py`: critical behavior validation
- `docker-compose.yml`, `Dockerfile`: local runtime
- `README.md`: operator/developer documentation

## 6) API/Frontend Consistency Checklist

When adding or renaming fields, update all of:

1. model field definition
2. serializer output in views
3. endpoint input parsing/validation
4. frontend form controls
5. frontend fetch payload construction
6. detail/popup rendering
7. tests
8. README endpoint docs/examples

## 7) Common Pitfalls to Avoid

- Using `[lat, lng]` accidentally in stored data.
- Returning geometry not compatible with Leaflet renderer.
- Forgetting CSRF header on POST/PATCH requests.
- Adding model fields without migration.
- Filtering only one feature type when both types should be filtered.
- Breaking Docker startup by changing container command without migration step.

## 8) Testing Expectations

At minimum before finalizing:

- `python manage.py test` passes in container.
- Existing tests still pass after schema/API changes.
- Added logic includes at least one targeted test.

Suggested extra checks:

- verify `/api/features/` with bbox and days filters
- verify photo uploads render in detail views
- verify distance recalculation on route update

## 9) Documentation Policy

Any of the following requires README update:

- new env vars
- endpoint path or payload changes
- setup workflow changes
- Docker behavior changes
- auth or permission model changes

Every feature PR must also update:

- `docs/FEATURES.md` (current feature behavior + acceptance criteria)
- `docs/QA_MATRIX.md` (coverage status, links, and notes)

All manual verification steps must be recorded in:

- `docs/MANUAL_TESTS.md`

## 10) Future Direction (Keep in Mind)

- Preserve invite-only workflow unless explicitly changed.
- Keep map interactions lightweight and responsive.
- Prefer incremental enhancements over large rewrites.
