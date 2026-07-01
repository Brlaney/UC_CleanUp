# Marketing Kit

Assets and copy for showcasing **Upper-Cumberland CleanUp** on social media.

Everything here is generated from the **local, seeded** app — the production
database is never touched.

## Regenerate the screenshots

1. Start the stack and seed realistic demo content (local only):
   ```bash
   docker compose up -d db web
   docker compose exec web python manage.py seed_district      # if not already seeded
   docker compose exec web python manage.py fetch_districts    # if not already seeded
   docker compose exec web python manage.py seed_demo --reset  # fills the map/leaderboard/etc.
   ```
2. Capture (Node + Playwright are in the repo `node_modules`):
   ```bash
   NODE_PATH=node_modules BASE_URL=http://localhost:8001 node marketing/capture.js
   ```
   Override `BASE_URL` if your web container maps to a different host port
   (check with `docker compose port web 8000`).

Output lands in `marketing/screenshots/` (git-ignored — regenerate anytime):

| File | Use |
|---|---|
| `desktop/map-overview.png` | Hero shot — the full active map |
| `desktop/cleanups.png` | Before/after gallery + impact banner |
| `desktop/leaderboard.png` | Ranked volunteers (All-Time) |
| `desktop/districts.png` | Per-district progress |
| `desktop/challenges.png` | Active challenge progress |
| `desktop/events.png` | Upcoming/past events |
| `mobile/map.png`, `mobile/cleanups.png` | Mobile-first shots for stories/reels |

The branded 1200×630 link-preview image lives at
`static/images/og-image.png` (used by the Open Graph tags site-wide).

## Draft post copy

See [`captions.md`](captions.md).

> Note: screenshots are generated from **demo/sample data** (`demo_*` users).
> Don't present seeded numbers as real program results in public posts —
> recapture once real activity exists, or use them as UI mockups.
