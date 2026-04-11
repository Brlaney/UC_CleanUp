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
from django.db.models import Count, Sum
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point, Polygon
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

User = get_user_model()

from django_ratelimit.decorators import ratelimit

from django.utils.text import slugify

from .models import ActivityLog, CleanupEvent, CleanupProof, District, EventRSVP, FeedbackEntry, Photo, Profile, PushSubscription, Team, TeamMembership, TrashSite, UserMapPreference
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

def _serialize_trash_site(site, user=None):
    proofs_qs = site.proofs.prefetch_related("photos", "created_by").all()
    area_geojson = None
    if site.area:
        area_geojson = json.loads(site.area.geojson)

    return {
        "id": str(site.id),
        "status": site.status,
        "title": site.title,
        "description": site.description,
        "severity": site.severity,
        "hazard_flag": site.hazard_flag,
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
    return render(request, "geoapp/profile.html", {
        "reports_count": reports_count,
        "cleanups_count": cleanups_count,
        "public_profile": profile.public_profile,
    })


def map_view(request):
    return render(request, "geoapp/map.html")


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
    districts = District.objects.filter(active=True)
    results = []
    for d in districts:
        results.append({
            "id": str(d.id),
            "name": d.name,
            "slug": d.slug,
            "description": d.description,
            "geometry": json.loads(d.geometry.geojson),
        })
    return JsonResponse({"districts": results})


@require_GET
def trash_site_detail_api(request, site_id):
    site = get_object_or_404(
        TrashSite.objects.select_related("created_by", "claimed_by", "verified_by", "team").prefetch_related(
            "proofs__photos", "proofs__created_by"
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
            "default_county": pref.default_county,
            "visible_district_slugs": pref.visible_district_slugs,
            "public_profile": profile.public_profile,
        })
    data = _load_payload(request)
    pref.default_county = str(data.get("default_county", "")).strip()
    slugs = data.get("visible_district_slugs")
    if isinstance(slugs, list):
        pref.visible_district_slugs = [str(s) for s in slugs]
    pref.save()
    if "public_profile" in data:
        profile.public_profile = _parse_bool(data.get("public_profile"))
        profile.save(update_fields=["public_profile"])
    return JsonResponse({
        "default_county": pref.default_county,
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
