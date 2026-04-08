# Production Release Plan — Upper-Cumberland CleanUp

## Status: Pre-production on `main` branch

---

## Phase 1 — Infrastructure (Blockers)

These must be resolved before any real users hit the app.

### 1.1 PostGIS Database
**Problem:** Render's `starter` database plan is plain PostgreSQL. GeoDjango requires PostGIS, or every spatial query and migration will fail at boot.

**Fix options (pick one):**
- **Supabase** — free tier includes PostGIS. Get the connection string, set `DATABASE_URL` in Render env vars.
- **Neon** — free tier, enable PostGIS extension manually after creating the DB.
- **Render paid DB** — upgrade to a plan that allows extensions, then run `CREATE EXTENSION postgis;` via their console.

**Action:** Provision a PostGIS-enabled DB, grab its connection string, and update `DATABASE_URL` in Render's environment variables dashboard.

---

### 1.2 Media Storage (Cloudflare R2)
**Problem:** `render.yaml` sets `USE_S3_MEDIA=1` but the R2 credentials are all `sync: false` (unpopulated). Photo uploads will fail silently or 500 in production.

**Action:**
1. Create a Cloudflare R2 bucket named `upper-cumberland-cleanup`.
2. Generate an R2 API token with Object Read & Write.
3. In Render's environment dashboard, fill in:
   - `AWS_ACCESS_KEY_ID` — R2 Access Key ID
   - `AWS_SECRET_ACCESS_KEY` — R2 Secret Access Key
   - `AWS_STORAGE_BUCKET_NAME` — `upper-cumberland-cleanup`
   - `AWS_S3_ENDPOINT_URL` — `https://<account-id>.r2.cloudflarestorage.com`
   - `AWS_S3_CUSTOM_DOMAIN` — your R2 public bucket domain (or leave blank to use the endpoint)

---

### 1.3 Run the Test Suite
**Problem:** The test suite was completely rewritten for the new architecture but has never been executed against a real DB.

**Action:** Start Docker Desktop and run:
```powershell
docker compose up -d db
docker compose run --rm web python manage.py test --verbosity=2
```
Fix any failures before deploying.

---

## Phase 2 — Security & Config

### 2.1 `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
Current `render.yaml` only allows `upper-cumberland-cleanup.onrender.com`. If you add a custom domain, update both env vars in Render's dashboard — not just in the yaml.

### 2.2 Create Superuser on First Deploy
Render doesn't have a one-time post-deploy hook. After first successful deploy:
```bash
# Via Render shell tab on the web service
python manage.py createsuperuser
```

### 2.3 Redis for Rate Limiting (Optional but Recommended)
Without Redis, `django-ratelimit` uses in-memory cache — limits won't be shared across Gunicorn workers. On Render you can add a Redis instance:
1. Add a Redis service in Render dashboard.
2. Set `REDIS_URL` env var to the internal Redis URL.

---

## Phase 3 — Seeding Districts on Production

The entrypoint auto-seeds Putnam County and District 3 from the GeoJSON files baked into the Docker image. This will run automatically on every deploy — it uses `update_or_create` so it's idempotent.

**Verify after first deploy** via `/api/districts/` — should return both `putnam-county` and `district-3`.

---

## Phase 4 — Custom Domain (Optional)

1. Add domain in Render dashboard → Custom Domains.
2. Update DNS at your registrar (CNAME → `upper-cumberland-cleanup.onrender.com`).
3. Update Render env vars:
   - `ALLOWED_HOSTS` → add your domain
   - `CSRF_TRUSTED_ORIGINS` → add `https://yourdomain.com`

---

## Phase 5 — Pre-Launch Checklist

- [ ] PostGIS DB provisioned and `DATABASE_URL` set in Render
- [ ] R2 bucket created and all 5 media env vars filled in Render
- [ ] Test suite passes locally (`python manage.py test`)
- [ ] First deploy succeeds — `/healthz` returns `{"ok": true, "database": "up"}`
- [ ] `/api/districts/` returns both district boundaries
- [ ] Superuser created via shell
- [ ] Photo upload works end-to-end (report a site with a photo)
- [ ] Mark cleaned with before/after photos works
- [ ] `/cleanups/` page shows completed cleanups
- [ ] Redis added (optional — do if rate limiting matters at launch)
- [ ] Custom domain configured (optional)

---

## Deployment Trigger

Render auto-deploys on push to `main` (set in `render.yaml` `autoDeploy: true`). Merging any PR to `main` triggers a deploy.

Current branch with all changes: `feat/district-3-pivot` (already merged to `main` per your note).

---

## Known Gaps (Post-Launch)

- **Password reset** — no email backend configured. Users cannot reset passwords yet. Needs `EMAIL_BACKEND` + SMTP or SendGrid env vars.
- **E2e Playwright tests** — `seedScreenshotDemo` management command was removed in the pivot. Smoke tests will fail in CI until updated.
- **Admin hardening** — consider restricting `/admin/` to staff-only IP ranges if exposed publicly.
- **Backup strategy** — Render starter DB has limited backup options. Consider daily export or upgrading the DB plan.
