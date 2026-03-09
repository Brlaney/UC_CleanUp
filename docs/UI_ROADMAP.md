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

## 3) Activity / Updates Feed Expansion

## Problem
Current UX now includes a basic updates feed, but it remains map-first. Users still need a richer event-ordered activity experience with stronger filtering, focus states, and moderation hooks.

## MVP Scope

### Data Model
- Extend the existing `ActivityLog` model with:
  - richer summaries
  - optional map viewport snapshot / focus metadata
  - optional denormalized county / campaign tags

### API Endpoints
- Extend `GET /api/activity/?page=1&page_size=25&days=7`
  - add richer filters (`type`, `user`, `county`)
- Add `GET /api/activity/<id>/`
  - full detail payload for selected entry

### UI Behavior
- Evolve existing `/updates/` page with:
  - filters (type/date/user)
  - stronger time-grouping and summaries
  - visual state for unresolved / high-priority changes
  - click card -> navigate to `/map/` and focus selected feature
- Optional split-view mode:
  - feed on left, mini-map on right
  - selecting entry pans/highlights target geometry

### MVP Done Criteria
- Feed supports useful filtering beyond newest-first.
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
