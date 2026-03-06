# UI / Product Roadmap (Future Only)

This document is intentionally forward-looking.  
Current implemented behavior is tracked in `docs/FEATURES.md`.

## 1) Palette and Visual System Plan

### MVP
- Define a small token set in CSS custom properties:
  - background, panel, text
  - semantic statuses: pending, in-progress, cleaned
  - route stroke + hover colors
- Improve contrast for marker colors against light OSM tiles.
- Standardize button color hierarchy (primary, secondary, destructive).

### Later
- Add colorblind-safe alternates for status markers.
- Add map style switching (light/high-contrast).
- Add design token theme profiles per campaign/event mode.

## 2) Styling Framework Evaluation

Goal: decide whether to keep custom CSS or adopt a framework for faster UI iteration.

### Candidates
- UIkit
  - Pros: fast component coverage, mature docs, easy class-based adoption.
  - Cons: opinionated visuals, potential override churn.
- Tailwind + component kit (for example DaisyUI/Headless mix)
  - Pros: high flexibility, good for tokenized design systems.
  - Cons: class-heavy templates, build pipeline complexity.
- Keep custom CSS (current approach)
  - Pros: zero new dependencies, direct control.
  - Cons: slower scaling for complex UI states/components.

### MVP Decision Criteria
- Works with Django templates without SPA rewrite.
- Minimal JS overhead.
- Supports responsive panel/modal patterns cleanly.
- Low migration risk from existing map page.

### Later
- Pilot framework in one new page (timeline feed) before broad migration.
- Add component inventory page (`/ui-kit/`) for consistency checks.

## 3) Timeline / Updates Feed Concept

## Problem
Current UX is map-first. Users need an event-ordered activity feed to quickly review recent cleanup actions and jump to map context.

## MVP Scope

### Data Model
- Introduce `ActivityLog` model (or materialized feed query) with:
  - `id`
  - `activity_type` (`TRASH_REPORTED`, `TRASH_CLEANED`, `ROUTE_LOGGED`, `PROOF_ADDED`)
  - `actor` (user FK)
  - `trash_site` nullable FK
  - `route_cleanup` nullable FK
  - `proof` nullable FK
  - `created_at`
  - optional denormalized summary text

### API Endpoints
- `GET /api/activity/?page=1&page_size=25&days=7`
  - newest-first list with enough geometry reference for map focus.
- `GET /api/activity/<id>/`
  - full detail payload for selected entry.

### UI Behavior
- New page `/updates/` with:
  - chronological cards
  - filters (type/date/user)
  - click card -> navigate to `/map/` and focus selected feature
- Optional split-view mode:
  - feed on left, mini-map on right
  - selecting entry pans/highlights target geometry

### MVP Done Criteria
- Feed shows last N cleanup/report events.
- Clicking event focuses correct map object.
- Data remains auth-protected and scoped to app users.

## Later
- Mentions/comments on activity.
- Confirmation workflow (`VERIFIED` by admin/mod).
- Rich diff display for field updates.
- Digest/notification hooks (email or push).

## 4) Prioritization Snapshot

### MVP Priority
1. Palette tokens and contrast cleanup.
2. Timeline feed backend + list UI.
3. Click-to-focus map integration from feed.

### Later Priority
1. Framework migration pilot.
2. Advanced timeline interactions and moderation extensions.
