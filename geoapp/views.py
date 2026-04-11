import base64
import csv
import io
import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.utils.dateparse import parse_datetime
from django.db.models import Count, Q, Sum
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point, Polygon
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_GET, require_http_methods

User = get_user_model()

from django_ratelimit.decorators import ratelimit

from django.utils.text import slugify

from .models import (
    ActivityLog, Badge, Challenge, CleanupEvent, CleanupProof, District,
    EventRSVP, FeedbackEntry, Photo, Profile, PushSubscription,
    ScheduledJobLog, Team, TeamMembership, TrashSite, UserBadge, UserMapPreference,
)
from .permissions import can_edit_trash_site, can_mark_cleaned, can_set_invalid_status, can_verify_cleanup, is_admin
from .services import assign_district, log_activity, notify_nearby_subscribers
from .validators import validate_photo_uploads


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_int(value, default=0):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_payload(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
    return request.POST


def _parse_bbox(raw_bbox):
    if not raw_bbox:
        return None
    parts = [p.strip() for p in raw_bbox.split(",")]
    if len(parts) != 4:
        return None
    try:
        min_lng, min_lat, max_lng, max_lat = map(float, parts)
    except ValueError:
        return None
    bbox = Polygon.from_bbox((min_lng, min_lat, max_lng, max_lat))
    bbox.srid = 4326
    return bbox


def _status_choices(status_csv):
    if not status_csv:
        return []
    allowed = set(TrashSite.Status.values)
    statuses = [s.strip().upper() for s in status_csv.split(",") if s.strip()]
    return [s for s in statuses if s in allowed]


def _days_to_cutoff(days_raw):
    if not days_raw or str(days_raw).lower() == "all":
        return None
    try:
        days = int(days_raw)
    except ValueError:
        return None
    return timezone.now() - timedelta(days=days)


def _photo_list_for_proof(proof):
    return [
        {
            "url": photo.image.url,
            "type": photo.photo_type,
        }
        for photo in proof.photos.all()
        if photo.image
    ]


def _photo_urls_grouped(proofs):
    """Return photos grouped by type: report, before, after."""
    groups = {"report": [], "before": [], "after": []}
    for proof in proofs:
        for photo in proof.photos.all():
            if photo.image:
                key = photo.photo_type.lower()
                if key in groups:
                    groups[key].append(photo.image.url)
                else:
                    groups["report"].append(photo.image.url)
    return groups


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _build_timeline(site):
    """Return a chronological list of lifecycle events for the site history timeline."""
    events = []

    # Reported
    events.append({
        "type": "reported",
        "label": "Reported",
        "by": site.created_by.username if site.created_by_id else "Anonymous",
        "at": site.created_at.isoformat(),
    })

    # Photos added (PROOF_ADDED activity logs) — one entry per unique proof
    logs = (
        site.activity_logs
        .select_related("actor", "proof")
        .order_by("created_at")
    )
    seen_proof_ids = set()
    for log in logs:
        if log.activity_type == ActivityLog.ActivityType.PROOF_ADDED and log.proof_id:
            if log.proof_id not in seen_proof_ids:
                seen_proof_ids.add(log.proof_id)
                events.append({
                    "type": "proof",
                    "label": "Photos Added",
                    "by": log.actor.username if log.actor_id else "Anonymous",
                    "at": log.created_at.isoformat(),
                })

    # Cleaned
    if site.cleaned_at:
        cleaner = None
        clean_log = logs.filter(activity_type=ActivityLog.ActivityType.TRASH_CLEANED).first()
        if clean_log and clean_log.actor_id:
            cleaner = clean_log.actor.username
        events.append({
            "type": "cleaned",
            "label": "Cleaned",
            "by": cleaner or "Unknown",
            "at": site.cleaned_at.isoformat(),
        })

    # Verified
    if site.verified_at:
        events.append({
            "type": "verified",
            "label": "Verified",
            "by": site.verified_by.username if site.verified_by_id else "Official",
            "at": site.verified_at.isoformat(),
        })

    # Flagged chronic
    if site.chronic_site:
        events.append({
            "type": "chronic",
            "label": "Flagged Chronic",
            "by": "System",
            "at": site.updated_at.isoformat(),
        })

    events.sort(key=lambda e: e["at"])
    return events


def _compute_trajectory(site):
    """Return improving/stable/worsening/resolved based on proof activity trends."""
    if site.status == TrashSite.Status.CLEANED:
        return "resolved"
    now = timezone.now()
    recent = site.proofs.filter(created_at__gte=now - timedelta(days=30)).count()
    prior_raw = site.proofs.filter(
        created_at__gte=now - timedelta(days=90),
        created_at__lt=now - timedelta(days=30),
    ).count()
    prior = prior_raw / 2.0  # normalize to 30-day equivalent
    if recent == 0 and prior == 0:
        return "stable"
    if prior == 0:
        return "worsening" if recent > 0 else "stable"
    if recent > prior * 1.25:
        return "worsening"
    if recent < prior * 0.75:
        return "improving"
    return "stable"


def _serialize_trash_site(site, user=None):
    proofs_qs = site.proofs.prefetch_related("photos", "created_by").all()
    area_geojson = None
    if site.area:
        area_geojson = json.loads(site.area.geojson)

    return {
        "id": str(site.id),
        "timeline": _build_timeline(site),
        "status": site.status,
        "title": site.title,
        "description": site.description,
        "severity": site.severity,
        "hazard_flag": site.hazard_flag,
        "chronic": site.chronic_site,
        "trajectory": _compute_trajectory(site),
        "created_by": site.created_by.username if site.created_by_id else "Anonymous",
        "claimed_by": site.claimed_by.username if site.claimed_by_id else None,
        "created_at": site.created_at.isoformat(),
        "updated_at": site.updated_at.isoformat(),
        "cleaned_at": site.cleaned_at.isoformat() if site.cleaned_at else None,
        "verified_by": site.verified_by.username if site.verified_by_id else None,
        "verified_at": site.verified_at.isoformat() if site.verified_at else None,
        "verification_note": site.verification_note,
        "work_order": site.work_order,
        "coordinates": [site.location.x, site.location.y],
        "area": area_geojson,
        "district": site.district.slug if site.district else None,
        "team": site.team.name if site.team_id else None,
        "team_slug": site.team.slug if site.team_id else None,
        "permissions": {
            "can_edit": can_edit_trash_site(user, site) if user and user.is_authenticated else False,
            "can_mark_cleaned": can_mark_cleaned(user, site) if user and user.is_authenticated else False,
            "can_invalidate": can_set_invalid_status(user) if user and user.is_authenticated else False,
            "can_verify": can_verify_cleanup(user) if user and user.is_authenticated else False,
        },
        "photos": _photo_urls_grouped(proofs_qs),
        "proofs": [
            {
                "id": str(proof.id),
                "note": proof.note,
                "bags_count": proof.bags_count,
                "created_by": proof.created_by.username if proof.created_by_id else "Anonymous",
                "created_at": proof.created_at.isoformat(),
                "photos": _photo_list_for_proof(proof),
            }
            for proof in proofs_qs
        ],
    }


def _site_to_feature(site, user=None):
    props = {
        "id": str(site.id),
        "type": "trash_site",
        "status": site.status,
        "title": site.title,
        "description": site.description,
        "severity": site.severity,
        "hazard_flag": site.hazard_flag,
        "chronic": site.chronic_site,
        "cleaned_at": site.cleaned_at.isoformat() if site.cleaned_at else None,
        "created_at": site.created_at.isoformat(),
        "has_area": bool(site.area),
        "photo_count": sum(p.photos.count() for p in site.proofs.all()),
    }
    if user and user.is_authenticated:
        props["can_mark_cleaned"] = can_mark_cleaned(user, site)
    else:
        props["can_mark_cleaned"] = False

    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [site.location.x, site.location.y]},
        "properties": props,
    }
    if site.area:
        feature["properties"]["area_geojson"] = json.loads(site.area.geojson)
    return feature


# ---------------------------------------------------------------------------
# HTML views
# ---------------------------------------------------------------------------

@login_required
def profile_view(request):
    reports_count = TrashSite.objects.filter(created_by=request.user).count()
    cleanups_count = CleanupProof.objects.filter(created_by=request.user).count()
    profile, _ = Profile.objects.get_or_create(user=request.user)
    user_badges = (
        UserBadge.objects.filter(user=request.user)
        .select_related("badge")
        .order_by("awarded_at")
    )
    return render(request, "geoapp/profile.html", {
        "reports_count": reports_count,
        "cleanups_count": cleanups_count,
        "public_profile": profile.public_profile,
        "user_badges": user_badges,
    })


def map_view(request):
    # Inline districts into the page to eliminate a critical-path XHR (290 KB payload).
    # Cached for 1 hour — district geometries change extremely rarely.
    districts_json = cache.get("districts_inline_json")
    if districts_json is None:
        districts_raw = []
        for d in District.objects.filter(active=True):
            districts_raw.append({
                "id": str(d.id),
                "name": d.name,
                "slug": d.slug,
                "description": d.description,
                "geometry": json.loads(d.geometry.geojson),
            })
        districts_json = json.dumps({"districts": districts_raw})
        cache.set("districts_inline_json", districts_json, 3600)
    return render(request, "geoapp/map.html", {"districts_json": districts_json})


def about_view(request):
    return render(request, "geoapp/about.html")


def cleanups_view(request):
    sites = (
        TrashSite.objects.filter(status=TrashSite.Status.CLEANED)
        .select_related("created_by")
        .prefetch_related("proofs__photos", "proofs__created_by")
        .order_by("-cleaned_at")
    )
    paginator = Paginator(sites, 12)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    items = []
    for site in page_obj:
        photos = _photo_urls_grouped(site.proofs.all())
        items.append({
            "id": str(site.id),
            "title": site.title or "Trash Site",
            "description": site.description,
            "severity": site.severity,
            "cleaned_at": site.cleaned_at,
            "created_by": site.created_by.username if site.created_by_id else "Anonymous",
            "bags_total": sum(p.bags_count for p in site.proofs.all()),
            "photos": photos,
        })

    return render(request, "geoapp/cleanups.html", {
        "items": items,
        "page_obj": page_obj,
    })


@require_GET
def healthz(request):
    try:
        connection.ensure_connection()
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=503)
    return JsonResponse({"ok": True, "database": "up"})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("/")
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("/")
    else:
        form = UserCreationForm()
    return render(request, "registration/signup.html", {"form": form})


def forgot_username_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if email:
            users = User.objects.filter(email__iexact=email)
            if users.exists():
                usernames = ", ".join(u.username for u in users)
                send_mail(
                    subject="Your District 3 CleanUp username",
                    message=(
                        f"Your username is: {usernames}\n\n"
                        "If you did not request this, you can ignore this email."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=True,
                )
        # Always show the done page — never reveal whether the email exists
        return render(request, "registration/forgot_username_done.html")
    return render(request, "registration/forgot_username.html")


# ---------------------------------------------------------------------------
# JSON API — public
# ---------------------------------------------------------------------------

@ratelimit(key="ip", rate="120/m", method="GET", block=True)
@require_GET
def features_api(request):
    bbox = _parse_bbox(request.GET.get("bbox", ""))
    status_filters = _status_choices(request.GET.get("status", ""))
    cutoff = _days_to_cutoff(request.GET.get("days", "all"))
    district_slug = request.GET.get("district", "").strip()

    trash_qs = TrashSite.objects.select_related("created_by").prefetch_related("proofs__photos")

    if bbox:
        trash_qs = trash_qs.filter(location__within=bbox)
    if status_filters:
        trash_qs = trash_qs.filter(status__in=status_filters)
    if cutoff:
        trash_qs = trash_qs.filter(created_at__gte=cutoff)
    if district_slug:
        trash_qs = trash_qs.filter(district__slug=district_slug)

    user = request.user if request.user.is_authenticated else None
    features = [_site_to_feature(site, user=user) for site in trash_qs]
    return JsonResponse({"type": "FeatureCollection", "features": features})


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
@require_GET
def districts_api(request):
    data = cache.get("districts_api_response")
    if data is None:
        results = []
        for d in District.objects.filter(active=True):
            results.append({
                "id": str(d.id),
                "name": d.name,
                "slug": d.slug,
                "description": d.description,
                "geometry": json.loads(d.geometry.geojson),
            })
        data = {"districts": results}
        cache.set("districts_api_response", data, 3600)
    resp = JsonResponse(data)
    resp["Cache-Control"] = "public, max-age=3600"
    return resp


@require_GET
def trash_site_detail_api(request, site_id):
    site = get_object_or_404(
        TrashSite.objects.select_related("created_by", "claimed_by", "verified_by", "team").prefetch_related(
            "proofs__photos", "proofs__created_by",
            "activity_logs__actor", "activity_logs__proof",
        ),
        id=site_id,
    )
    user = request.user if request.user.is_authenticated else None
    return JsonResponse(_serialize_trash_site(site, user=user))


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
@require_GET
def impact_api(request):
    data = cache.get("impact_stats")
    if data is None:
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        bags = CleanupProof.objects.aggregate(total=Sum("bags_count"))["total"] or 0
        sites_cleaned = TrashSite.objects.filter(status=TrashSite.Status.CLEANED).count()
        sites_reported = TrashSite.objects.count()
        reporters = set(
            TrashSite.objects.filter(created_at__gte=month_start, created_by__isnull=False)
            .values_list("created_by_id", flat=True)
        )
        cleaners = set(
            CleanupProof.objects.filter(created_at__gte=month_start, created_by__isnull=False)
            .values_list("created_by_id", flat=True)
        )
        data = {
            "bags_collected": bags,
            "sites_cleaned": sites_cleaned,
            "sites_reported": sites_reported,
            "active_volunteers_this_month": len(reporters | cleaners),
        }
        cache.set("impact_stats", data, 300)  # 5-minute cache
    return JsonResponse(data)


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
@require_GET
def heatmap_api(request):
    _INTENSITY = {"LIGHT": 0.3, "MEDIUM": 0.6, "HEAVY": 1.0}
    sites = (
        TrashSite.objects
        .exclude(status=TrashSite.Status.CLEANED)
        .only("location", "severity")
    )
    points = [
        [site.location.y, site.location.x, _INTENSITY.get(site.severity, 0.5)]
        for site in sites
    ]
    return JsonResponse({"points": points})


def share_view(request, site_id):
    site = get_object_or_404(
        TrashSite.objects.prefetch_related("proofs__photos"),
        id=site_id,
    )
    og_image = None
    # Prefer an AFTER photo, then any photo
    for proof in site.proofs.all():
        for photo in proof.photos.filter(photo_type=Photo.PhotoType.AFTER):
            if photo.image:
                og_image = request.build_absolute_uri(photo.image.url)
                break
        if og_image:
            break
    if not og_image:
        for proof in site.proofs.all():
            for photo in proof.photos.all():
                if photo.image:
                    og_image = request.build_absolute_uri(photo.image.url)
                    break
            if og_image:
                break

    map_url = request.build_absolute_uri("/?focus_id=" + str(site.id))
    return render(request, "geoapp/share.html", {
        "site": site,
        "og_image": og_image,
        "share_url": request.build_absolute_uri(),
        "map_url": map_url,
    })


@ratelimit(key="ip", rate="60/m", method="GET", block=True)
@require_GET
def cleanups_list_api(request):
    page_number = request.GET.get("page", "1")
    page_size_raw = request.GET.get("page_size", "20")

    sites = (
        TrashSite.objects.filter(status=TrashSite.Status.CLEANED)
        .select_related("created_by")
        .prefetch_related("proofs__photos", "proofs__created_by")
        .order_by("-cleaned_at")
    )

    try:
        page_size = max(1, min(int(page_size_raw), 50))
    except ValueError:
        page_size = 20

    paginator = Paginator(sites, page_size)
    page_obj = paginator.get_page(page_number)

    results = []
    for site in page_obj:
        photos = _photo_urls_grouped(site.proofs.all())
        results.append({
            "id": str(site.id),
            "title": site.title,
            "description": site.description,
            "severity": site.severity,
            "cleaned_at": site.cleaned_at.isoformat() if site.cleaned_at else None,
            "created_by": site.created_by.username if site.created_by_id else "Anonymous",
            "bags_total": sum(p.bags_count for p in site.proofs.all()),
            "photos": photos,
        })

    return JsonResponse({
        "count": paginator.count,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "results": results,
    })


# ---------------------------------------------------------------------------
# JSON API — authenticated
# ---------------------------------------------------------------------------

@login_required
@ratelimit(key="user", rate="10/h", method="POST", block=True)
@require_http_methods(["POST"])
def trash_site_create_api(request):
    data = _load_payload(request)
    geojson_raw = data.get("geojson")
    point = None
    area = None

    if geojson_raw:
        if isinstance(geojson_raw, str):
            try:
                geojson_raw = json.loads(geojson_raw)
            except json.JSONDecodeError:
                return _json_error("Invalid GeoJSON payload.")

        geom_type = geojson_raw.get("type", "")

        if geom_type == "Point":
            coords = geojson_raw.get("coordinates", [])
            if len(coords) != 2:
                return _json_error("Invalid Point coordinates.")
            point = Point(float(coords[0]), float(coords[1]), srid=4326)

        elif geom_type == "Polygon":
            try:
                area = GEOSGeometry(json.dumps(geojson_raw), srid=4326)
                if not isinstance(area, Polygon):
                    return _json_error("Invalid Polygon geometry.")
                point = area.centroid
                point.srid = 4326
            except Exception:
                return _json_error("Invalid Polygon geometry.")

        else:
            return _json_error("geojson type must be Point or Polygon.")
    else:
        try:
            lat = float(data.get("lat"))
            lng = float(data.get("lng"))
        except (TypeError, ValueError):
            return _json_error("lat and lng are required.")
        point = Point(lng, lat, srid=4326)

    severity = str(data.get("severity", "")).upper()
    if severity and severity not in TrashSite.Severity.values:
        return _json_error("Invalid severity.")

    photos = request.FILES.getlist("photos")
    try:
        validate_photo_uploads(photos)
    except ValidationError as exc:
        return _json_error(str(exc.message))

    district = assign_district(point)
    team_slug = str(data.get("team", "")).strip()
    team = Team.objects.filter(slug=team_slug).first() if team_slug else None

    site = TrashSite.objects.create(
        location=point,
        area=area,
        district=district,
        title=data.get("title", "").strip(),
        description=data.get("description", "").strip(),
        severity=severity,
        hazard_flag=_parse_bool(data.get("hazard_flag"), default=False),
        created_by=request.user,
        team=team,
    )

    if photos:
        proof = CleanupProof.objects.create(
            trash_site=site,
            note="Initial report photos",
            bags_count=0,
            created_by=request.user,
        )
        for image in photos:
            Photo.objects.create(proof=proof, image=image, photo_type=Photo.PhotoType.REPORT)
        log_activity(
            ActivityLog.ActivityType.PROOF_ADDED,
            request.user,
            trash_site=site,
            proof=proof,
            summary=f"{request.user.username} attached report photos.",
        )

    log_activity(
        ActivityLog.ActivityType.TRASH_REPORTED,
        request.user,
        trash_site=site,
        summary=f"{request.user.username} reported a trash site.",
    )

    try:
        notify_nearby_subscribers(site)
    except Exception:
        pass

    return JsonResponse(_serialize_trash_site(site, user=request.user), status=201)


@login_required
@require_http_methods(["GET", "PATCH"])
def trash_site_update_api(request, site_id):
    site = get_object_or_404(TrashSite, id=site_id)

    if request.method == "GET":
        return JsonResponse(_serialize_trash_site(site, user=request.user))

    if not can_edit_trash_site(request.user, site):
        return _json_error("You do not have permission to edit this trash site.", status=403)

    data = _load_payload(request)

    status = str(data.get("status", site.status)).upper()
    if status not in TrashSite.Status.values:
        return _json_error("Invalid status.")
    if status == TrashSite.Status.INVALID and not can_set_invalid_status(request.user):
        return _json_error("Only admins can invalidate trash sites.", status=403)
    site.status = status

    if "title" in data:
        site.title = str(data.get("title", "")).strip()
    if "description" in data:
        site.description = str(data.get("description", "")).strip()
    if "severity" in data:
        severity = str(data.get("severity", "")).upper()
        if severity and severity not in TrashSite.Severity.values:
            return _json_error("Invalid severity.")
        site.severity = severity
    if "hazard_flag" in data:
        site.hazard_flag = _parse_bool(data.get("hazard_flag"))

    if site.status == TrashSite.Status.CLEANED and not site.cleaned_at:
        site.cleaned_at = timezone.now()
    if site.status != TrashSite.Status.CLEANED:
        site.cleaned_at = None
    site.save()

    log_activity(
        ActivityLog.ActivityType.TRASH_UPDATED,
        request.user,
        trash_site=site,
        summary=f"{request.user.username} updated a trash site.",
    )
    return JsonResponse(_serialize_trash_site(site, user=request.user))


@login_required
@ratelimit(key="user", rate="10/h", method="POST", block=True)
@require_http_methods(["POST"])
def trash_site_mark_cleaned_api(request, site_id):
    site = get_object_or_404(TrashSite, id=site_id)
    if not can_mark_cleaned(request.user, site):
        return _json_error("You do not have permission to mark this site cleaned.", status=403)

    note = request.POST.get("note", "").strip()
    bags_count = _coerce_int(request.POST.get("bags_count"), default=0)
    before_photos = request.FILES.getlist("before_photos")
    after_photos = request.FILES.getlist("after_photos")
    team_slug = request.POST.get("team", "").strip()
    proof_team = Team.objects.filter(slug=team_slug).first() if team_slug else None

    try:
        validate_photo_uploads(before_photos)
        validate_photo_uploads(after_photos)
    except ValidationError as exc:
        return _json_error(str(exc.message))

    proof = CleanupProof.objects.create(
        trash_site=site,
        note=note,
        bags_count=max(0, bags_count),
        created_by=request.user,
        team=proof_team,
    )
    for image in before_photos:
        Photo.objects.create(proof=proof, image=image, photo_type=Photo.PhotoType.BEFORE)
    for image in after_photos:
        Photo.objects.create(proof=proof, image=image, photo_type=Photo.PhotoType.AFTER)

    site.status = TrashSite.Status.CLEANED
    site.cleaned_at = timezone.now()
    site.save(update_fields=["status", "cleaned_at", "updated_at"])

    log_activity(
        ActivityLog.ActivityType.TRASH_CLEANED,
        request.user,
        trash_site=site,
        proof=proof,
        summary=f"{request.user.username} marked a trash site cleaned.",
    )

    return JsonResponse(_serialize_trash_site(site, user=request.user))


@login_required
@require_http_methods(["GET", "POST"])
def preferences_api(request):
    pref, _ = UserMapPreference.objects.get_or_create(user=request.user)
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "GET":
        return JsonResponse({
            "default_county": pref.default_county,   # legacy
            "default_counties": pref.default_counties,
            "visible_district_slugs": pref.visible_district_slugs,
            "public_profile": profile.public_profile,
        })
    data = _load_payload(request)
    counties = data.get("default_counties")
    if isinstance(counties, list):
        pref.default_counties = [str(c) for c in counties]
    slugs = data.get("visible_district_slugs")
    if isinstance(slugs, list):
        pref.visible_district_slugs = [str(s) for s in slugs]
    pref.save()
    if "public_profile" in data:
        profile.public_profile = _parse_bool(data.get("public_profile"))
        profile.save(update_fields=["public_profile"])
    return JsonResponse({
        "default_counties": pref.default_counties,
        "visible_district_slugs": pref.visible_district_slugs,
        "public_profile": profile.public_profile,
    })


@login_required
@ratelimit(key="user", rate="5/h", method="POST", block=True)
@require_http_methods(["POST"])
def feedback_create_api(request):
    data = _load_payload(request)
    feedback_type = str(data.get("feedback_type", FeedbackEntry.FeedbackType.GENERAL)).upper().strip()
    message = str(data.get("message", "")).strip()
    page_url = str(data.get("page_url", "")).strip()

    if feedback_type not in FeedbackEntry.FeedbackType.values:
        return _json_error("Invalid feedback type.")
    if not message:
        return _json_error("message is required.")

    entry = FeedbackEntry.objects.create(
        feedback_type=feedback_type,
        message=message,
        page_url=page_url,
        created_by=request.user,
    )
    return JsonResponse(
        {
            "id": str(entry.id),
            "feedback_type": entry.feedback_type,
            "status": entry.status,
            "message": entry.message,
            "page_url": entry.page_url,
            "created_at": entry.created_at.isoformat(),
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def trash_site_verify_api(request, site_id):
    if not can_verify_cleanup(request.user):
        return _json_error("You do not have permission to verify cleanups.", status=403)
    site = get_object_or_404(TrashSite.objects.select_related("verified_by"), id=site_id)
    if site.status != TrashSite.Status.CLEANED:
        return _json_error("Only CLEANED sites can be verified.")
    data = _load_payload(request)
    site.verified_by = request.user
    site.verified_at = timezone.now()
    site.verification_note = str(data.get("verification_note", "")).strip()
    site.work_order = str(data.get("work_order", "")).strip()
    site.save(update_fields=["verified_by", "verified_at", "verification_note", "work_order", "updated_at"])
    return JsonResponse(_serialize_trash_site(site, user=request.user))


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
@require_GET
def leaderboard_api(request):
    period = request.GET.get("period", "month")
    proof_qs = CleanupProof.objects.filter(created_by__isnull=False)
    if period == "month":
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        proof_qs = proof_qs.filter(created_at__gte=month_start)

    top = (
        proof_qs
        .values("created_by")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    results = []
    for i, row in enumerate(top):
        user = User.objects.filter(pk=row["created_by"]).select_related("profile").first()
        if not user:
            continue
        profile = getattr(user, "profile", None)
        public = bool(profile and profile.public_profile)
        results.append({
            "rank": i + 1,
            "username": user.username if public else "Anonymous",
            "count": row["count"],
        })

    return JsonResponse({"period": period, "results": results})


def leaderboard_view(request):
    return render(request, "geoapp/leaderboard.html")


# ---------------------------------------------------------------------------
# Cleanup Events
# ---------------------------------------------------------------------------

def _serialize_event(event, user=None):
    rsvp_count = event.rsvps.count()
    user_has_rsvp = False
    if user and user.is_authenticated:
        user_has_rsvp = event.rsvps.filter(user=user).exists()
    full = bool(event.max_attendees and rsvp_count >= event.max_attendees)
    can_complete = False
    if user and user.is_authenticated:
        can_complete = is_admin(user) or bool(event.organizer_id and event.organizer_id == user.id)
    return {
        "id": str(event.id),
        "title": event.title,
        "description": event.description,
        "event_date": event.event_date.isoformat(),
        "status": event.status,
        "organizer": event.organizer.username if event.organizer_id else "Anonymous",
        "rsvp_count": rsvp_count,
        "max_attendees": event.max_attendees,
        "is_full": full,
        "user_has_rsvp": user_has_rsvp,
        "coordinates": [event.location.x, event.location.y],
        "district": event.district.slug if event.district else None,
        "permissions": {"can_complete": can_complete},
    }


@ratelimit(key="ip", rate="60/m", block=True)
@require_http_methods(["GET", "POST"])
def events_list_api(request):
    if request.method == "GET":
        status_filter = request.GET.get("status", "SCHEDULED")
        qs = CleanupEvent.objects.select_related("organizer", "district").prefetch_related("rsvps")
        if status_filter:
            statuses = [s.strip().upper() for s in status_filter.split(",")]
            qs = qs.filter(status__in=statuses)
        user = request.user if request.user.is_authenticated else None
        paginator = Paginator(qs, 20)
        page_obj = paginator.get_page(request.GET.get("page", "1"))
        return JsonResponse({
            "count": paginator.count,
            "page": page_obj.number,
            "num_pages": paginator.num_pages,
            "results": [_serialize_event(ev, user) for ev in page_obj],
        })

    # POST — create event
    if not request.user.is_authenticated:
        return _json_error("Authentication required.", status=401)
    data = _load_payload(request)
    title = str(data.get("title", "")).strip()
    if not title:
        return _json_error("title is required.")
    try:
        lat = float(data.get("lat"))
        lng = float(data.get("lng"))
    except (TypeError, ValueError):
        return _json_error("lat and lng are required.")
    event_date_raw = str(data.get("event_date", "")).strip()
    if not event_date_raw:
        return _json_error("event_date is required.")
    try:
        event_date = parse_datetime(event_date_raw)
        if not event_date:
            raise ValueError()
        if timezone.is_naive(event_date):
            event_date = timezone.make_aware(event_date)
    except (ValueError, TypeError):
        return _json_error("event_date must be a valid ISO datetime.")

    location = Point(lng, lat, srid=4326)
    district = assign_district(location)
    max_attendees_raw = data.get("max_attendees")
    max_attendees = _coerce_int(max_attendees_raw) if max_attendees_raw else None

    event = CleanupEvent.objects.create(
        title=title,
        description=str(data.get("description", "")).strip(),
        location=location,
        district=district,
        event_date=event_date,
        max_attendees=max_attendees,
        organizer=request.user,
    )
    return JsonResponse(_serialize_event(event, user=request.user), status=201)


@ratelimit(key="ip", rate="60/m", method="GET", block=True)
@require_GET
def event_detail_api(request, event_id):
    event = get_object_or_404(
        CleanupEvent.objects.select_related("organizer", "district").prefetch_related("rsvps"),
        id=event_id,
    )
    user = request.user if request.user.is_authenticated else None
    return JsonResponse(_serialize_event(event, user=user))


@require_http_methods(["POST", "DELETE"])
def event_rsvp_api(request, event_id):
    if not request.user.is_authenticated:
        return _json_error("Authentication required.", status=401)
    event = get_object_or_404(CleanupEvent.objects.prefetch_related("rsvps"), id=event_id)
    if event.status != CleanupEvent.Status.SCHEDULED:
        return _json_error("This event is no longer accepting RSVPs.")

    if request.method == "POST":
        if event.rsvps.filter(user=request.user).exists():
            return _json_error("You have already RSVP'd to this event.")
        rsvp_count = event.rsvps.count()
        if event.max_attendees and rsvp_count >= event.max_attendees:
            return _json_error("This event is full.")
        rsvp = EventRSVP.objects.create(event=event, user=request.user)
        if request.user.email:
            try:
                body = render_to_string("email/event_rsvp_confirmation.html", {
                    "event": event, "user": request.user,
                })
                send_mail(
                    subject=f"You're signed up for {event.title}!",
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[request.user.email],
                    fail_silently=True,
                )
            except Exception:
                pass
        return JsonResponse({"rsvp_id": str(rsvp.id), "rsvp_count": event.rsvps.count()})

    # DELETE — cancel RSVP
    deleted, _ = event.rsvps.filter(user=request.user).delete()
    if not deleted:
        return _json_error("No RSVP found to cancel.", status=404)
    return JsonResponse({"rsvp_count": event.rsvps.count()})


@login_required
@require_http_methods(["POST"])
def event_complete_api(request, event_id):
    event = get_object_or_404(CleanupEvent, id=event_id)
    can_complete = is_admin(request.user) or bool(event.organizer_id and event.organizer_id == request.user.id)
    if not can_complete:
        return _json_error("Only the organizer or an admin can complete this event.", status=403)
    if event.status != CleanupEvent.Status.SCHEDULED:
        return _json_error("Event is not SCHEDULED.")
    event.status = CleanupEvent.Status.COMPLETED
    event.save(update_fields=["status", "updated_at"])
    return JsonResponse(_serialize_event(event, user=request.user))


def events_view(request):
    return render(request, "geoapp/events.html")


# ---------------------------------------------------------------------------
# Teams (Phase 4A)
# ---------------------------------------------------------------------------

def _serialize_team(team, user=None):
    member_count = team.memberships.count()
    site_count = team.trash_sites.count()
    cleanup_count = team.cleanup_proofs.count()
    bags_total = team.cleanup_proofs.aggregate(total=Sum("bags_count"))["total"] or 0
    is_member = False
    is_leader = False
    if user and user.is_authenticated:
        membership = team.memberships.filter(user=user).first()
        if membership:
            is_member = True
            is_leader = membership.role == TeamMembership.Role.LEADER
    return {
        "id": str(team.id),
        "name": team.name,
        "slug": team.slug,
        "description": team.description,
        "org_type": team.org_type,
        "leader": team.leader.username if team.leader_id else None,
        "district": team.district.slug if team.district_id else None,
        "member_count": member_count,
        "site_count": site_count,
        "cleanup_count": cleanup_count,
        "bags_total": bags_total,
        "is_member": is_member,
        "is_leader": is_leader,
    }


@ratelimit(key="ip", rate="60/m", block=True)
@require_http_methods(["GET", "POST"])
def team_list_api(request):
    if request.method == "GET":
        teams = Team.objects.select_related("leader", "district").prefetch_related("memberships", "cleanup_proofs")
        user = request.user if request.user.is_authenticated else None
        results = [_serialize_team(t, user) for t in teams]
        return JsonResponse({"count": len(results), "results": results})

    if not request.user.is_authenticated:
        return _json_error("Authentication required.", status=401)
    data = _load_payload(request)
    name = str(data.get("name", "")).strip()
    if not name:
        return _json_error("name is required.")
    raw_slug = str(data.get("slug", "")).strip().lower()
    team_slug = raw_slug if raw_slug else slugify(name)
    if Team.objects.filter(slug=team_slug).exists():
        return _json_error("A team with this slug already exists.")
    org_type = str(data.get("org_type", "OTHER")).upper()
    if org_type not in Team.OrgType.values:
        org_type = "OTHER"
    district_slug = str(data.get("district", "")).strip()
    district = District.objects.filter(slug=district_slug).first() if district_slug else None
    team = Team.objects.create(
        name=name,
        slug=team_slug,
        description=str(data.get("description", "")).strip(),
        org_type=org_type,
        district=district,
        leader=request.user,
    )
    TeamMembership.objects.create(team=team, user=request.user, role=TeamMembership.Role.LEADER)
    return JsonResponse(_serialize_team(team, user=request.user), status=201)


@ratelimit(key="ip", rate="60/m", method="GET", block=True)
@require_GET
def team_detail_api(request, team_slug):
    team = get_object_or_404(
        Team.objects.select_related("leader", "district").prefetch_related("memberships", "cleanup_proofs"),
        slug=team_slug,
    )
    user = request.user if request.user.is_authenticated else None
    return JsonResponse(_serialize_team(team, user))


@login_required
@require_http_methods(["POST"])
def team_join_api(request, team_slug):
    team = get_object_or_404(Team.objects.prefetch_related("memberships"), slug=team_slug)
    if team.memberships.filter(user=request.user).exists():
        return _json_error("You are already a member of this team.")
    TeamMembership.objects.create(team=team, user=request.user, role=TeamMembership.Role.MEMBER)
    return JsonResponse(_serialize_team(team, user=request.user))


def teams_list_view(request):
    return render(request, "geoapp/teams.html")


def team_view(request, team_slug):
    team = get_object_or_404(Team, slug=team_slug)
    return render(request, "geoapp/team.html", {"team": team})


def team_certificate_view(request, team_slug):
    team = get_object_or_404(Team, slug=team_slug)
    stats = {
        "site_count": team.trash_sites.count(),
        "cleanup_count": team.cleanup_proofs.count(),
        "bags_total": team.cleanup_proofs.aggregate(total=Sum("bags_count"))["total"] or 0,
        "member_count": team.memberships.count(),
    }
    return render(request, "geoapp/team_certificate.html", {"team": team, "stats": stats})


# ---------------------------------------------------------------------------
# Push Notifications (Phase 4C)
# ---------------------------------------------------------------------------

@require_GET
def push_vapid_key_api(request):
    key = getattr(settings, "VAPID_PUBLIC_KEY", "")
    if not key:
        return _json_error("Push notifications not configured.", status=503)
    return JsonResponse({"vapid_public_key": key})


@require_http_methods(["POST"])
def push_subscribe_api(request):
    data = _load_payload(request)
    endpoint = str(data.get("endpoint", "")).strip()
    p256dh = str(data.get("p256dh", "")).strip()
    auth_key = str(data.get("auth", "")).strip()
    if not (endpoint and p256dh and auth_key):
        return _json_error("endpoint, p256dh, and auth are required.")
    lat = data.get("lat")
    lng = data.get("lng")
    location = None
    if lat is not None and lng is not None:
        try:
            location = Point(float(lng), float(lat), srid=4326)
        except (TypeError, ValueError):
            pass
    try:
        radius = float(data.get("radius_miles", 2.0))
    except (TypeError, ValueError):
        radius = 2.0
    user = request.user if request.user.is_authenticated else None
    sub, created = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": user,
            "p256dh": p256dh,
            "auth_key": auth_key,
            "saved_location": location,
            "notification_radius_miles": radius,
        },
    )
    return JsonResponse({"subscribed": True}, status=201 if created else 200)


@require_http_methods(["POST", "DELETE"])
def push_unsubscribe_api(request):
    data = _load_payload(request)
    endpoint = str(data.get("endpoint", "")).strip()
    if not endpoint:
        return _json_error("endpoint is required.")
    PushSubscription.objects.filter(endpoint=endpoint).delete()
    return JsonResponse({"unsubscribed": True})


# ---------------------------------------------------------------------------
# Service Worker (Phase 4B)
# ---------------------------------------------------------------------------

@require_GET
def service_worker_view(request):
    from django.template.loader import get_template
    template = get_template("sw.js")
    content = template.render({"STATIC_URL": settings.STATIC_URL}, request)
    resp = HttpResponse(content, content_type="application/javascript; charset=utf-8")
    resp["Service-Worker-Allowed"] = "/"
    resp["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


# ---------------------------------------------------------------------------
# Phase 5B — Cron health check
# ---------------------------------------------------------------------------

@require_GET
def healthz_cron(request):
    jobs = ScheduledJobLog.objects.all()
    data = {}
    for job in jobs:
        data[job.job_name] = {
            "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
            "last_success_at": job.last_success_at.isoformat() if job.last_success_at else None,
            "status": job.last_status,
            "last_error": job.last_error or None,
        }
    return JsonResponse({"jobs": data})


# ---------------------------------------------------------------------------
# Phase 5E — Badges
# ---------------------------------------------------------------------------

@require_GET
def badges_api(request):
    """Public list of all available badges with user earn status."""
    user = request.user if request.user.is_authenticated else None
    earned_slugs = set()
    if user:
        earned_slugs = set(
            UserBadge.objects.filter(user=user).values_list("badge__slug", flat=True)
        )
    badges = Badge.objects.all()
    return JsonResponse({
        "results": [
            {
                "slug": b.slug,
                "name": b.name,
                "description": b.description,
                "icon": b.icon,
                "earned": b.slug in earned_slugs,
            }
            for b in badges
        ]
    })


# ---------------------------------------------------------------------------
# Phase 5F — Seasonal challenges
# ---------------------------------------------------------------------------

def _serialize_challenge(challenge):
    from django.db.models import Sum as DSum
    bags = CleanupProof.objects.filter(
        created_at__date__gte=challenge.start_date,
        created_at__date__lte=challenge.end_date,
    ).aggregate(total=DSum("bags_count"))["total"] or 0
    sites = TrashSite.objects.filter(
        created_at__date__gte=challenge.start_date,
        created_at__date__lte=challenge.end_date,
        status=TrashSite.Status.CLEANED,
    ).count()
    progress = min(100, round(bags / challenge.bag_goal * 100)) if challenge.bag_goal else 0
    return {
        "id": str(challenge.id),
        "name": challenge.name,
        "slug": challenge.slug,
        "description": challenge.description,
        "start_date": challenge.start_date.isoformat(),
        "end_date": challenge.end_date.isoformat(),
        "bag_goal": challenge.bag_goal,
        "bags_collected": bags,
        "sites_cleaned": sites,
        "progress_pct": progress,
        "status": challenge.status,
    }


@ratelimit(key="ip", rate="60/m", method="GET", block=True)
@require_GET
def challenges_list_api(request):
    qs = Challenge.objects.exclude(status=Challenge.Status.COMPLETED)
    return JsonResponse({"results": [_serialize_challenge(c) for c in qs]})


@ratelimit(key="ip", rate="60/m", method="GET", block=True)
@require_GET
def challenge_detail_api(request, challenge_slug):
    challenge = get_object_or_404(Challenge, slug=challenge_slug)
    return JsonResponse(_serialize_challenge(challenge))


def challenges_view(request):
    return render(request, "geoapp/challenges.html")


# ---------------------------------------------------------------------------
# Phase 5H — Embeddable map widget
# ---------------------------------------------------------------------------

@xframe_options_exempt
def embed_map_view(request):
    return render(request, "geoapp/embed.html")


# ---------------------------------------------------------------------------
# Phase 5I — Event flyer with QR code
# ---------------------------------------------------------------------------

@require_GET
def event_flyer_view(request, event_id):
    event = get_object_or_404(CleanupEvent, id=event_id)
    rsvp_url = request.build_absolute_uri(f"/events/")
    fmt = request.GET.get("format", "html")

    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(rsvp_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        qr_data_url = f"data:image/png;base64,{qr_b64}"
    except ImportError:
        qr_data_url = None

    if fmt == "png" and qr_data_url:
        img_bytes = base64.b64decode(qr_b64)
        return HttpResponse(img_bytes, content_type="image/png")

    lat = event.location.y
    lng = event.location.x
    map_thumb = (
        f"https://staticmap.openstreetmap.de/staticmap.php"
        f"?center={lat},{lng}&zoom=14&size=400x200&maptype=mapnik"
        f"&markers={lat},{lng},red-pushpin"
    )

    return render(request, "geoapp/event_flyer.html", {
        "event": event,
        "qr_data_url": qr_data_url,
        "rsvp_url": rsvp_url,
        "map_thumb": map_thumb,
    })


# ---------------------------------------------------------------------------
# Phase 6A — Coordinator Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard_view(request):
    if not can_verify_cleanup(request.user):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Dashboard restricted to coordinators and admins.")

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Summary cards
    pending_count = TrashSite.objects.filter(status=TrashSite.Status.PENDING).count()
    in_progress_count = TrashSite.objects.filter(status=TrashSite.Status.IN_PROGRESS).count()
    awaiting_verification = TrashSite.objects.filter(
        status=TrashSite.Status.CLEANED, verified_at__isnull=True
    ).count()
    chronic_count = TrashSite.objects.filter(chronic_site=True).count()
    bags_this_month = (
        CleanupProof.objects.filter(created_at__gte=month_start)
        .aggregate(total=Sum("bags_count"))["total"] or 0
    )
    new_volunteers_this_month = (
        User.objects.filter(date_joined__gte=month_start).count()
    )

    # Pending verifications (CLEANED + not verified)
    pending_verifications = (
        TrashSite.objects
        .filter(status=TrashSite.Status.CLEANED, verified_at__isnull=True)
        .select_related("created_by", "district")
        .order_by("cleaned_at")[:50]
    )

    # Chronic sites
    chronic_sites = (
        TrashSite.objects
        .filter(chronic_site=True)
        .select_related("created_by", "district")
        .order_by("created_at")[:50]
    )

    # Per-district breakdown
    districts = District.objects.filter(active=True).order_by("name")
    district_breakdown = []
    for d in districts:
        qs = d.trash_sites
        district_breakdown.append({
            "district": d,
            "pending": qs.filter(status=TrashSite.Status.PENDING).count(),
            "cleaned": qs.filter(status=TrashSite.Status.CLEANED).count(),
            "chronic": qs.filter(chronic_site=True).count(),
            "total": qs.count(),
        })

    # Recent ActivityLog
    recent_activity = (
        ActivityLog.objects
        .select_related("actor", "trash_site")
        .order_by("-created_at")[:20]
    )

    return render(request, "geoapp/dashboard.html", {
        "pending_count": pending_count,
        "in_progress_count": in_progress_count,
        "awaiting_verification": awaiting_verification,
        "chronic_count": chronic_count,
        "bags_this_month": bags_this_month,
        "new_volunteers_this_month": new_volunteers_this_month,
        "pending_verifications": pending_verifications,
        "chronic_sites": chronic_sites,
        "district_breakdown": district_breakdown,
        "recent_activity": recent_activity,
    })


# ---------------------------------------------------------------------------
# Phase 6B — Data Export
# ---------------------------------------------------------------------------

@login_required
def export_sites_view(request, fmt):
    if fmt not in ("csv", "geojson"):
        from django.http import Http404
        raise Http404

    # Auth-based queryset scoping
    status_param = request.GET.get("status", "")
    district_slug = request.GET.get("district", "").strip()
    since_raw = request.GET.get("since", "").strip()

    qs = TrashSite.objects.select_related("created_by", "district", "verified_by")

    if can_verify_cleanup(request.user):
        # COORDINATOR/ADMIN: can export all statuses
        statuses = _status_choices(status_param) if status_param else []
        if statuses:
            qs = qs.filter(status__in=statuses)
    else:
        # Regular auth users: own reports only
        qs = qs.filter(created_by=request.user)
        statuses = _status_choices(status_param) if status_param else []
        if statuses:
            qs = qs.filter(status__in=statuses)

    if district_slug:
        qs = qs.filter(district__slug=district_slug)

    if since_raw:
        from django.utils.dateparse import parse_date
        since = parse_date(since_raw)
        if since:
            qs = qs.filter(created_at__date__gte=since)

    qs = qs.prefetch_related("proofs").order_by("-created_at")

    if fmt == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="uc-cleanup-sites.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "id", "title", "status", "severity", "hazard", "district",
            "lat", "lng", "bags_total", "created_at", "cleaned_at", "verified", "chronic",
        ])
        for site in qs:
            bags = sum(p.bags_count for p in site.proofs.all())
            writer.writerow([
                str(site.id),
                site.title,
                site.status,
                site.severity,
                "yes" if site.hazard_flag else "no",
                site.district.slug if site.district_id else "",
                site.location.y,
                site.location.x,
                bags,
                site.created_at.isoformat(),
                site.cleaned_at.isoformat() if site.cleaned_at else "",
                "yes" if site.verified_at else "no",
                "yes" if site.chronic_site else "no",
            ])
        return response

    # GeoJSON
    features = []
    for site in qs:
        bags = sum(p.bags_count for p in site.proofs.all())
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [site.location.x, site.location.y]},
            "properties": {
                "id": str(site.id),
                "title": site.title,
                "status": site.status,
                "severity": site.severity,
                "hazard": site.hazard_flag,
                "district": site.district.slug if site.district_id else None,
                "bags_total": bags,
                "created_at": site.created_at.isoformat(),
                "cleaned_at": site.cleaned_at.isoformat() if site.cleaned_at else None,
                "verified": bool(site.verified_at),
                "chronic": site.chronic_site,
            },
        })
    payload = json.dumps({"type": "FeatureCollection", "features": features}, indent=2)
    response = HttpResponse(payload, content_type="application/geo+json")
    response["Content-Disposition"] = 'attachment; filename="uc-cleanup-sites.geojson"'
    return response


# ---------------------------------------------------------------------------
# Phase 6C — District Stats Pages
# ---------------------------------------------------------------------------

@ratelimit(key="ip", rate="60/m", method="GET", block=True)
@require_GET
def district_stats_api(request, district_slug):
    district = get_object_or_404(District, slug=district_slug, active=True)
    qs = district.trash_sites

    site_count = qs.count()
    cleaned_count = qs.filter(status=TrashSite.Status.CLEANED).count()
    pending_count = qs.filter(status__in=[TrashSite.Status.PENDING, TrashSite.Status.IN_PROGRESS]).count()
    chronic_count = qs.filter(chronic_site=True).count()
    bags_total = (
        CleanupProof.objects.filter(trash_site__district=district)
        .aggregate(total=Sum("bags_count"))["total"] or 0
    )

    # Top 3 cleanup submitters in this district
    top_vols_qs = (
        CleanupProof.objects
        .filter(trash_site__district=district, created_by__isnull=False)
        .values("created_by__username", "created_by__profile__public_profile")
        .annotate(count=Count("id"))
        .order_by("-count")[:3]
    )
    top_volunteers = []
    for row in top_vols_qs:
        pub = row.get("created_by__profile__public_profile", False)
        top_volunteers.append({
            "username": row["created_by__username"] if pub else "Anonymous",
            "count": row["count"],
        })

    # Recent 5 cleanups
    recent_cleanups_qs = (
        qs.filter(status=TrashSite.Status.CLEANED)
        .select_related("created_by")
        .order_by("-cleaned_at")[:5]
    )
    recent_cleanups = [
        {
            "id": str(s.id),
            "title": s.title or "Trash Site",
            "cleaned_at": s.cleaned_at.isoformat() if s.cleaned_at else None,
            "cleaned_by": s.created_by.username if s.created_by_id else "Anonymous",
        }
        for s in recent_cleanups_qs
    ]

    return JsonResponse({
        "slug": district.slug,
        "name": district.name,
        "site_count": site_count,
        "cleaned_count": cleaned_count,
        "pending_count": pending_count,
        "chronic_count": chronic_count,
        "bags_total": bags_total,
        "top_volunteers": top_volunteers,
        "recent_cleanups": recent_cleanups,
    })


def districts_list_view(request):
    return render(request, "geoapp/districts.html")


def district_detail_view(request, district_slug):
    district = get_object_or_404(District, slug=district_slug, active=True)
    return render(request, "geoapp/district_detail.html", {"district": district})
