import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point, Polygon
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from django_ratelimit.decorators import ratelimit

from .models import ActivityLog, CleanupProof, District, FeedbackEntry, Photo, TrashSite
from .permissions import can_edit_trash_site, can_mark_cleaned, can_set_invalid_status, is_admin
from .services import assign_district, log_activity
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
        "created_by": site.created_by.username,
        "claimed_by": site.claimed_by.username if site.claimed_by else None,
        "created_at": site.created_at.isoformat(),
        "updated_at": site.updated_at.isoformat(),
        "cleaned_at": site.cleaned_at.isoformat() if site.cleaned_at else None,
        "coordinates": [site.location.x, site.location.y],
        "area": area_geojson,
        "district": site.district.slug if site.district else None,
        "permissions": {
            "can_edit": can_edit_trash_site(user, site) if user and user.is_authenticated else False,
            "can_mark_cleaned": can_mark_cleaned(user, site) if user and user.is_authenticated else False,
            "can_invalidate": can_set_invalid_status(user) if user and user.is_authenticated else False,
        },
        "photos": _photo_urls_grouped(proofs_qs),
        "proofs": [
            {
                "id": str(proof.id),
                "note": proof.note,
                "bags_count": proof.bags_count,
                "created_by": proof.created_by.username,
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
            "created_by": site.created_by.username,
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
        TrashSite.objects.select_related("created_by", "claimed_by").prefetch_related(
            "proofs__photos", "proofs__created_by"
        ),
        id=site_id,
    )
    user = request.user if request.user.is_authenticated else None
    return JsonResponse(_serialize_trash_site(site, user=user))


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
            "created_by": site.created_by.username,
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

    site = TrashSite.objects.create(
        location=point,
        area=area,
        district=district,
        title=data.get("title", "").strip(),
        description=data.get("description", "").strip(),
        severity=severity,
        hazard_flag=_parse_bool(data.get("hazard_flag"), default=False),
        created_by=request.user,
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
