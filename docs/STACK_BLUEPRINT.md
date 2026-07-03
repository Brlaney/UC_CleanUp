# Stack Blueprint — Reusable Django + Vanilla JS Scaffold

> ⚠️ **This is NOT documentation for UC CleanUp.** It is a generic, reusable
> blueprint that abstracts this project's *structural skeleton* (settings layout,
> auth/`Profile` pattern, function-based views, vanilla-JS `fetch` wrappers,
> Docker/Render pipeline) so the same architecture can be reused to build a
> **different** app in a different domain. The worked example below builds a
> **blog**. For how *this* app actually works, see [`SUMMARY.md`](SUMMARY.md),
> the root [`AGENTS.md`](../AGENTS.md), and the root [`README.md`](../README.md).

This document describes the architecture of a production Django web application
as a reusable blueprint: keep the same frontend/backend structure and tooling,
swap in completely different domain logic.

---

## What This Architecture Is

A server-rendered Django 5.2 app with a Vanilla JS frontend, PostGIS database,
and Docker-based deployment on Render.com. There is no React, Vue, or any SPA
framework. The UI is driven by Django templates + async `fetch()` calls.

The original site is a community geo-mapping tool. The goal for the new project
is a **blog** with the same structural skeleton: same deployment pipeline, same
auth patterns, same frontend communication style, same tooling — just different
content and models.

---

## Stack at a Glance

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | Django 5.2 |
| Database | PostgreSQL 16 (no PostGIS needed for a blog) |
| Auth | Django built-in auth + custom Profile model |
| Frontend | Django templates (Jinja2-like syntax) + Vanilla JS |
| CSS | Plain CSS with CSS variables (no Tailwind, no Bootstrap) |
| Media storage | Cloudflare R2 (S3-compatible) via `django-storages` |
| Static files | WhiteNoise (served from Django process in prod) |
| WSGI server | Gunicorn |
| Deployment | Render.com via `render.yaml` (Docker service) |
| Containerization | Docker + Docker Compose for local dev |
| E2E Testing | Playwright |

---

## Project Directory Layout

```
myproject/
├── myproject/                  # Django project package
│   ├── settings.py             # All configuration (env-driven)
│   ├── urls.py                 # Root URL routing
│   ├── wsgi.py
│   └── asgi.py
├── myapp/                      # Main Django application
│   ├── models.py               # All database models
│   ├── views.py                # All view functions (HTML + JSON API)
│   ├── urls.py                 # App-level URL routing
│   ├── permissions.py          # Role/auth helper functions
│   ├── services.py             # Business logic (side effects, complex ops)
│   ├── signals.py              # Django signals for auto-creating related objects
│   ├── middleware.py           # Custom middleware
│   ├── admin.py                # Django admin registration
│   ├── validators.py           # Custom field validators
│   ├── management/
│   │   └── commands/           # Custom manage.py commands
│   ├── migrations/             # Auto-generated migration files
│   └── tests.py                # Unit and integration tests
├── templates/                  # Django HTML templates
│   ├── base.html               # Root layout (navbar, footer, toast container)
│   ├── registration/           # Login, signup, password reset
│   ├── email/                  # Transactional email templates
│   └── myapp/                  # All page templates
├── static/
│   ├── js/
│   │   ├── base.js             # Global UI utilities (modals, toasts, settings)
│   │   └── utils.js            # CSRF helper, JSON fetch wrapper
│   ├── css/
│   │   ├── site.css            # Main styles + responsive layout
│   │   └── palette.css         # CSS custom properties (color tokens)
│   ├── images/
│   └── manifest.json           # PWA manifest (optional)
├── docker/
│   └── web-entrypoint.sh       # Container startup script
├── e2e/                        # Playwright E2E tests
├── docker-compose.yml
├── Dockerfile
├── render.yaml                 # Render.com deployment config
├── requirements.txt
├── package.json                # Only for E2E tooling
├── playwright.config.js
└── manage.py
```

---

## Settings Architecture (`settings.py`)

All configuration is environment-variable-driven. There is one `settings.py`
file — no dev/prod split into separate files. The env vars toggle behavior.

```python
import os, dj_database_url

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = os.getenv("DEBUG", "0") == "1"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "myapp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",    # Serve static from process
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Database — parse from DB_CONN_STRING (Supabase style) or POSTGRES_* vars
DATABASES = {"default": dj_database_url.config(env="DB_CONN_STRING") or {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.getenv("POSTGRES_DB"),
    "USER": os.getenv("POSTGRES_USER"),
    "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
    "HOST": os.getenv("POSTGRES_HOST", "localhost"),
    "PORT": os.getenv("POSTGRES_PORT", "5432"),
}}

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media files — local in dev, Cloudflare R2 in production
if os.getenv("USE_S3_MEDIA") == "1":
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_ACCESS_KEY_ID = os.environ["CF_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = os.environ["CF_SECRET_ACCESS_KEY"]
    AWS_STORAGE_BUCKET_NAME = os.environ["CF_BUCKET_NAME"]
    AWS_S3_ENDPOINT_URL = os.environ["CF_S3_ENDPOINT_URL"]
    AWS_S3_CUSTOM_DOMAIN = os.getenv("CF_S3_CUSTOM_DOMAIN")
else:
    MEDIA_ROOT = BASE_DIR / "media"
    MEDIA_URL = "/media/"

# Security (enabled in production)
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
```

---

## Authentication Setup

### User Model
Use the default `django.contrib.auth.models.User`. Do **not** create a custom
user model — extend via a `Profile` model with a `OneToOneField`.

### Profile Model (required pattern)
```python
class Profile(models.Model):
    class Role(models.TextChoices):
        MEMBER = "MEMBER"
        EDITOR = "EDITOR"       # Rename roles to match your domain
        ADMIN  = "ADMIN"

    user      = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role      = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    bio       = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### Auto-create Profile on signup (signals.py)
```python
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
```

### Auth URLs
```python
# myproject/urls.py
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("accounts/login/",    auth_views.LoginView.as_view(),    name="login"),
    path("accounts/logout/",   auth_views.LogoutView.as_view(),   name="logout"),
    path("accounts/signup/",   views.signup_view,                 name="signup"),
    path("accounts/password/", include("django.contrib.auth.urls")),
]
```

### Permission Helpers (permissions.py)
```python
def is_admin(user):
    return user.is_authenticated and (
        user.is_superuser or
        hasattr(user, "profile") and user.profile.role == Profile.Role.ADMIN
    )

def can_edit_post(user, post):
    return user.is_authenticated and (post.author == user or is_admin(user))

def can_publish(user):
    return user.is_authenticated and user.profile.role in (
        Profile.Role.EDITOR, Profile.Role.ADMIN
    )
```

---

## Database Models (Blog Domain)

All PKs are UUIDs. Use `auto_now_add=True` / `auto_now=True` for timestamps.

```python
import uuid
from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

class Tag(models.Model):
    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)

class Post(models.Model):
    class Status(models.TextChoices):
        DRAFT     = "DRAFT"
        PUBLISHED = "PUBLISHED"
        ARCHIVED  = "ARCHIVED"

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title      = models.CharField(max_length=255)
    slug       = models.SlugField(unique=True)
    body       = models.TextField()
    excerpt    = models.TextField(blank=True)
    cover      = models.ImageField(upload_to="covers/%Y/%m/%d/", blank=True)
    status     = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    author     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="posts")
    category   = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="posts")
    tags       = models.ManyToManyField(Tag, blank=True, related_name="posts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

class Comment(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post       = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    body       = models.TextField()
    approved   = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Reaction(models.Model):
    # One reaction per user per post (unique_together enforced)
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post    = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reactions")
    user    = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji   = models.CharField(max_length=10)    # e.g. "👍", "❤️", "🔥"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("post", "user")

class Newsletter(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email      = models.EmailField(unique=True)
    confirmed  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class FeedbackEntry(models.Model):
    class FeedbackType(models.TextChoices):
        BUG     = "BUG"
        REQUEST = "REQUEST"
        GENERAL = "GENERAL"

    class Status(models.TextChoices):
        OPEN         = "OPEN"
        ACKNOWLEDGED = "ACKNOWLEDGED"
        CLOSED       = "CLOSED"

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feedback_type = models.CharField(max_length=20, choices=FeedbackType.choices)
    status        = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    message       = models.TextField()
    page_url      = models.URLField(blank=True)
    created_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
```

---

## URL Routing

```python
# myapp/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Public HTML pages
    path("",                           views.home,           name="home"),
    path("blog/",                      views.post_list,      name="post_list"),
    path("blog/<slug:slug>/",          views.post_detail,    name="post_detail"),
    path("category/<slug:slug>/",      views.category_posts, name="category_posts"),
    path("tag/<slug:slug>/",           views.tag_posts,      name="tag_posts"),
    path("about/",                     views.about,          name="about"),
    path("profile/",                   views.profile,        name="profile"),

    # Public JSON APIs
    path("api/posts/",                 views.api_posts,              name="api_posts"),
    path("api/posts/<uuid:pk>/",       views.api_post_detail,        name="api_post_detail"),
    path("api/categories/",            views.api_categories,         name="api_categories"),
    path("api/tags/",                  views.api_tags,               name="api_tags"),

    # Auth-required APIs
    path("api/posts/<uuid:pk>/react/", views.api_react,              name="api_react"),
    path("api/posts/<uuid:pk>/comment/", views.api_comment,          name="api_comment"),
    path("api/feedback/",              views.api_feedback,           name="api_feedback"),
    path("api/newsletter/subscribe/",  views.api_newsletter,         name="api_newsletter"),

    # Admin-only APIs
    path("api/posts/create/",          views.api_create_post,        name="api_create_post"),
    path("api/posts/<uuid:pk>/update/", views.api_update_post,       name="api_update_post"),
    path("api/comments/<uuid:pk>/approve/", views.api_approve_comment, name="api_approve_comment"),

    # Health check
    path("healthz",                    views.healthz,                name="healthz"),
]
```

---

## Views Pattern

All views are function-based. HTML views return `render()`. API views return
`JsonResponse`. Never mix both in one function.

```python
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django_ratelimit.decorators import ratelimit

# HTML page view
def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug, status=Post.Status.PUBLISHED)
    comments = post.comments.filter(approved=True).select_related("author")
    return render(request, "myapp/post_detail.html", {
        "post": post,
        "comments": comments,
    })

# JSON API view
@ratelimit(key="ip", rate="60/m", method="GET", block=True)
def api_posts(request):
    qs = Post.objects.filter(status="PUBLISHED").select_related("author", "category")
    search = request.GET.get("q", "")
    if search:
        qs = qs.filter(title__icontains=search)
    return JsonResponse({"posts": [_serialize_post(p) for p in qs]})

# Auth-required API view
@login_required
@require_http_methods(["POST"])
def api_react(request, pk):
    import json
    post = get_object_or_404(Post, pk=pk, status="PUBLISHED")
    data = json.loads(request.body)
    emoji = data.get("emoji", "")
    if not emoji:
        return _json_error("emoji is required", status=400)
    Reaction.objects.update_or_create(post=post, user=request.user, defaults={"emoji": emoji})
    return JsonResponse({"ok": True})

# Helper: consistent error responses
def _json_error(message, status=400):
    return JsonResponse({"error": message}, status=status)

# Helper: model → JSON dict
def _serialize_post(post):
    return {
        "id": str(post.id),
        "title": post.title,
        "slug": post.slug,
        "excerpt": post.excerpt,
        "author": post.author.username if post.author else None,
        "category": post.category.name if post.category else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
    }
```

---

## Frontend Communication Pattern

There is **no** API client library. All requests go through `utils.js`:

```javascript
// static/js/utils.js

function getCsrfToken() {
    return document.querySelector('[name=csrf-token]').content;
}

async function apiPost(url, data) {
    const res = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify(data),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "Request failed");
    return json;
}

async function apiGet(url) {
    const res = await fetch(url);
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "Request failed");
    return json;
}
```

CSRF token is injected in `base.html`:
```html
<meta name="csrf-token" content="{{ csrf_token }}">
```

Toast notifications and modal state live in `base.js`:
```javascript
// static/js/base.js

function showToast(message, type = "success") {
    const el = document.createElement("div");
    el.className = `toast toast--${type}`;
    el.textContent = message;
    document.getElementById("toast-container").appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

function openModal(id)  { document.getElementById(id).classList.remove("hidden"); }
function closeModal(id) { document.getElementById(id).classList.add("hidden"); }
```

---

## Template Structure

```html
<!-- templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token }}">
    <link rel="stylesheet" href="{% static 'css/palette.css' %}">
    <link rel="stylesheet" href="{% static 'css/site.css' %}">
    <title>{% block title %}My Blog{% endblock %}</title>
</head>
<body>
    <nav>...</nav>
    <main>{% block content %}{% endblock %}</main>
    <div id="toast-container"></div>
    <footer>...</footer>
    <script src="{% static 'js/utils.js' %}"></script>
    <script src="{% static 'js/base.js' %}"></script>
    {% block extra_js %}{% endblock %}
</body>
</html>
```

Each page template extends `base.html` and puts page-specific JS in `extra_js`.

---

## Rate Limiting

```python
# Applied per-IP on public endpoints, per-user on authenticated endpoints
from django_ratelimit.decorators import ratelimit

@ratelimit(key="ip",   rate="120/m", method="GET",  block=True)  # public reads
@ratelimit(key="user", rate="30/m",  method="POST", block=True)  # authenticated writes
```

When exceeded, Django returns `429 Too Many Requests`.

---

## Docker Setup

### Dockerfile
```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
ENTRYPOINT ["bash", "docker/web-entrypoint.sh"]
```

### docker/web-entrypoint.sh
```bash
#!/bin/bash
set -e

python manage.py migrate --noinput

if [ "$RUN_COLLECTSTATIC" = "1" ]; then
    python manage.py collectstatic --noinput --clear
fi

if [ "$DEBUG" = "1" ]; then
    exec python manage.py runserver 0.0.0.0:8000
else
    exec gunicorn myproject.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-2}" \
        --log-level "${LOG_LEVEL:-info}"
fi
```

### docker-compose.yml
```yaml
version: "3.9"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: myapp
      POSTGRES_PASSWORD: myapp
    ports: ["5432:5432"]
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U myapp"]
      interval: 5s
      retries: 5

  web:
    build: .
    depends_on:
      db:
        condition: service_healthy
    environment:
      DEBUG: "1"
      SECRET_KEY: dev-only-secret-key
      POSTGRES_DB: myapp
      POSTGRES_USER: myapp
      POSTGRES_PASSWORD: myapp
      POSTGRES_HOST: db
      POSTGRES_PORT: "5432"
      RUN_COLLECTSTATIC: "0"
    ports: ["8000:8000"]
    volumes: [".:/app"]

volumes:
  postgres_data:
```

---

## Render.com Deployment (`render.yaml`)

```yaml
services:
  - type: web
    name: my-blog
    runtime: docker
    plan: starter
    healthCheckPath: /healthz
    envVars:
      - key: SECRET_KEY
        generateValue: true
      - key: DEBUG
        value: "0"
      - key: ALLOWED_HOSTS
        value: "my-blog.com,www.my-blog.com,my-blog.onrender.com"
      - key: CSRF_TRUSTED_ORIGINS
        value: "https://my-blog.com,https://www.my-blog.com,https://my-blog.onrender.com"
      - key: DB_CONN_STRING
        sync: false       # Set manually in Render dashboard
      - key: DATABASE_SSL_REQUIRE
        value: "1"
      - key: GUNICORN_WORKERS
        value: "2"
      - key: RUN_COLLECTSTATIC
        value: "1"
      - key: USE_S3_MEDIA
        value: "1"
      - key: CF_ACCESS_KEY_ID
        sync: false
      - key: CF_SECRET_ACCESS_KEY
        sync: false
      - key: CF_BUCKET_NAME
        sync: false
      - key: CF_S3_ENDPOINT_URL
        sync: false
      - key: CF_S3_CUSTOM_DOMAIN
        sync: false
    preDeployCommand: "python manage.py migrate --noinput"
```

The database is hosted on **Supabase** (free-tier PostgreSQL). The connection
string goes in `DB_CONN_STRING`. Media uploads go to **Cloudflare R2** (free
10 GB/month). Both integrate with Render at no cost on a starter plan.

---

## Environment Variables Reference

```bash
# .env (local dev)
SECRET_KEY=change-me-in-production
DEBUG=1
ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000

# Database (local — matched to docker-compose)
POSTGRES_DB=myapp
POSTGRES_USER=myapp
POSTGRES_PASSWORD=myapp
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
DATABASE_SSL_REQUIRE=0
CONN_MAX_AGE=60

# Server
WEB_PORT=8000
GUNICORN_WORKERS=2
LOG_LEVEL=INFO
RUN_COLLECTSTATIC=0

# Media (set to 1 and fill CF_ vars in production)
USE_S3_MEDIA=0
CF_ACCESS_KEY_ID=
CF_SECRET_ACCESS_KEY=
CF_BUCKET_NAME=
CF_S3_ENDPOINT_URL=
CF_S3_CUSTOM_DOMAIN=

# Optional
REDIS_URL=    # Enables Redis-backed rate limit caching
```

---

## Key Dependencies (`requirements.txt`)

```
Django>=5.2,<6.0
psycopg[binary]>=3.1,<4.0
Pillow>=10.0,<12.0
gunicorn>=23.0,<24.0
whitenoise>=6.8,<7.0
dj-database-url>=2.2,<3.0
django-storages>=1.14,<2.0
boto3>=1.35,<2.0
django-ratelimit>=4.1,<5.0
```

---

## Notable Patterns to Carry Over

### UUIDs as Primary Keys
```python
id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
```
Prevents sequential ID enumeration attacks.

### Caching Expensive Queries
```python
from django.core.cache import cache

def api_categories(request):
    data = cache.get("categories_list")
    if data is None:
        data = [{"name": c.name, "slug": c.slug} for c in Category.objects.all()]
        cache.set("categories_list", data, 3600)
    return JsonResponse({"categories": data})
```

### Signals for Side Effects
```python
# Automatically send welcome email on first signup
@receiver(post_save, sender=User)
def on_user_created(sender, instance, created, **kwargs):
    if created:
        send_welcome_email(instance)
```

### Soft Deletion via Status Field
Never `delete()` user-submitted content. Change `status` to `ARCHIVED` instead.
This preserves audit history and allows undo.

### Query Optimization
Always use `select_related()` for FK fields and `prefetch_related()` for
reverse/M2M relations to avoid N+1 queries:
```python
Post.objects.filter(status="PUBLISHED") \
    .select_related("author", "category") \
    .prefetch_related("tags", "comments")
```

---

## What to Build (Blog-Specific Roadmap)

Implement features in this order to have a functional site at each checkpoint:

1. **Post listing + detail pages** (read-only, no auth required)
2. **Category and tag filtering** (public API endpoints)
3. **Signup/login/logout** (Django auth + custom signup view)
4. **Post reactions** (emoji picker, one reaction per user per post)
5. **Comments** (submit + admin approval flow)
6. **Author/editor role** (Profile.role, can draft and publish posts)
7. **Admin dashboard** (unapproved comments, feedback entries)
8. **Newsletter signup** (email capture, confirmation email)
9. **Feedback widget** (floating button on every page, FeedbackEntry model)
10. **Search** (simple `icontains` query, no Elasticsearch needed to start)

---

## What to Omit for a Blog

The original project used these; a blog does **not** need them:

- GeoDjango / PostGIS — no spatial data
- Leaflet or any map library
- Service worker / offline sync
- Web Push notifications
- PWA manifest
- GeoJSON export
- ArcGIS or external GIS API calls
- Custom IP ban middleware (use Render's DDoS protection instead)
