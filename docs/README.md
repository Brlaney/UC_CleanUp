# Documentation Index

Start here. This maps every doc to its purpose and says which one is
**authoritative** for a given topic, so there's a single source of truth per
subject and no guessing across overlapping files.

| Doc | Purpose | Authoritative for |
|---|---|---|
| [`../README.md`](../README.md) | Project front door: what it is, screenshots, quickstart, tech stack | First-time setup, high-level overview |
| [`../AGENTS.md`](../AGENTS.md) | Contributor & coding-agent contract: rules, file-ownership map, pitfalls | **How to make changes safely** (geo rules, API/FE consistency) |
| [`SUMMARY.md`](SUMMARY.md) | Canonical product + architecture deep-dive (all phases, model graph, security, infra) | **What the app does and how it's built** |
| [`FEATURES.md`](FEATURES.md) | Core map/report/cleanup feature catalog with acceptance criteria (F-001 … F-024) | Core-flow behavior + "done when" |
| [`PLAN.md`](PLAN.md) | Production deploy/runbook (PostGIS, R2, env vars, pre-launch checklist) | **Deploying to Render** |
| [`UI_ROADMAP.md`](UI_ROADMAP.md) | Forward-looking product/UI roadmap (not yet implemented) | Future work only |
| [`QA_MATRIX.md`](QA_MATRIX.md) | Test-coverage inventory keyed to feature IDs | What's covered by which test |
| [`MANUAL_TESTS.md`](MANUAL_TESTS.md) | Repeatable manual test scripts (MT-001 …) | Manual QA steps |
| [`STACK_BLUEPRINT.md`](STACK_BLUEPRINT.md) | ⚠️ Reusable scaffold for building a **different** app on this stack | **Not this app** — generic blueprint |

## Source of truth for code-level contracts

Docs describe intent; when in doubt, the code wins. For exact contracts:

- **API endpoints / routes** → [`../geoapp/urls.py`](../geoapp/urls.py)
- **Database schema & geometry** → [`../geoapp/models.py`](../geoapp/models.py)
- **Roles & permissions** → [`../geoapp/permissions.py`](../geoapp/permissions.py)
- **Environment variables** → [`../putnam_trashmap/settings.py`](../putnam_trashmap/settings.py) + [`../.env.example`](../.env.example)
- **Deploy config** → [`../render.yaml`](../render.yaml), [`../docker/web-entrypoint.sh`](../docker/web-entrypoint.sh)

## Naming note

Three names refer to the same project, for historical reasons:
**`putnam_trashmap`** (Django project package) · **`geoapp`** (the Django app) ·
**Upper Cumberland CleanUp / UC CleanUp** (the product, at `uc-cleanup.com`).
