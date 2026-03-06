import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import LineString, Point, Polygon
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .models import CleanupProof, Photo, RouteCleanup, TrashSite


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


def _photo_urls_for_proofs(proofs):
    urls = []
    for proof in proofs:
        for photo in proof.photos.all():
            if photo.image:
                urls.append(photo.image.url)
    return urls


def _serialize_trash_site(site):
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
        "photos": _photo_urls_for_proofs(site.proofs.prefetch_related("photos")),
        "proofs": [
            {
                "id": str(proof.id),
                "note": proof.note,
                "bags_count": proof.bags_count,
                "created_by": proof.created_by.username,
                "created_at": proof.created_at.isoformat(),
                "photos": [photo.image.url for photo in proof.photos.all() if photo.image],
            }
            for proof in site.proofs.prefetch_related("photos", "created_by").all()
        ],
    }


def _serialize_route(route):
    return {
        "id": str(route.id),
        "status": route.status,
        "notes": route.notes,
        "distance_miles": route.distance_miles,
        "time_spent_minutes": route.time_spent_minutes,
        "created_by": route.created_by.username,
        "created_at": route.created_at.isoformat(),
        "coordinates": list(route.geometry.coords),
        "photos": _photo_urls_for_proofs(route.proofs.prefetch_related("photos")),
        "proofs": [
            {
                "id": str(proof.id),
                "note": proof.note,
                "bags_count": proof.bags_count,
                "created_by": proof.created_by.username,
                "created_at": proof.created_at.isoformat(),
                "photos": [photo.image.url for photo in proof.photos.all() if photo.image],
            }
            for proof in route.proofs.prefetch_related("photos", "created_by").all()
        ],
    }


def _site_to_feature(site):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [site.location.x, site.location.y]},
        "properties": {
            "id": str(site.id),
            "type": "trash_site",
            "status": site.status,
            "title": site.title,
            "description": site.description,
            "severity": site.severity,
            "hazard_flag": site.hazard_flag,
            "cleaned_at": site.cleaned_at.isoformat() if site.cleaned_at else None,
            "created_at": site.created_at.isoformat(),
        },
    }


def _route_to_feature(route):
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[coord[0], coord[1]] for coord in route.geometry.coords],
        },
        "properties": {
            "id": str(route.id),
            "type": "route_cleanup",
            "status": route.status,
            "notes": route.notes,
            "distance_miles": route.distance_miles,
            "time_spent_minutes": route.time_spent_minutes,
            "created_at": route.created_at.isoformat(),
        },
    }


@login_required
def home(request):
    return redirect("map")


@login_required
def map_view(request):
    return render(request, "geoapp/map.html")


@login_required
@require_GET
def features_api(request):
    bbox = _parse_bbox(request.GET.get("bbox", ""))
    status_filters = _status_choices(request.GET.get("status", ""))
    cutoff = _days_to_cutoff(request.GET.get("days", "all"))

    trash_qs = TrashSite.objects.select_related("created_by")
    route_qs = RouteCleanup.objects.select_related("created_by")

    if bbox:
        trash_qs = trash_qs.filter(location__within=bbox)
        route_qs = route_qs.filter(geometry__intersects=bbox)
    if status_filters:
        trash_qs = trash_qs.filter(status__in=status_filters)
    if cutoff:
        trash_qs = trash_qs.filter(created_at__gte=cutoff)
        route_qs = route_qs.filter(created_at__gte=cutoff)

    features = [_site_to_feature(site) for site in trash_qs] + [_route_to_feature(route) for route in route_qs]
    return JsonResponse({"type": "FeatureCollection", "features": features})


@login_required
@require_http_methods(["POST"])
def trash_site_create_api(request):
    data = _load_payload(request)
    geojson = data.get("geojson")
    point = None

    if geojson:
        if isinstance(geojson, str):
            try:
                geojson = json.loads(geojson)
            except json.JSONDecodeError:
                return _json_error("Invalid GeoJSON payload.")
        coords = geojson.get("coordinates", [])
        if len(coords) != 2:
            return _json_error("Invalid GeoJSON coordinates.")
        point = Point(float(coords[0]), float(coords[1]), srid=4326)
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

    site = TrashSite.objects.create(
        location=point,
        title=data.get("title", "").strip(),
        description=data.get("description", "").strip(),
        severity=severity,
        hazard_flag=_parse_bool(data.get("hazard_flag"), default=False),
        created_by=request.user,
    )

    photos = request.FILES.getlist("photos")
    if photos:
        proof = CleanupProof.objects.create(
            trash_site=site,
            note="Initial report photos",
            bags_count=0,
            created_by=request.user,
        )
        for image in photos:
            Photo.objects.create(proof=proof, image=image)

    return JsonResponse(_serialize_trash_site(site), status=201)


@login_required
@require_http_methods(["GET", "PATCH"])
def trash_site_update_api(request, site_id):
    site = get_object_or_404(TrashSite, id=site_id)
    if request.method == "GET":
        return JsonResponse(_serialize_trash_site(site))

    data = _load_payload(request)

    status = str(data.get("status", site.status)).upper()
    if status not in TrashSite.Status.values:
        return _json_error("Invalid status.")
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
    return JsonResponse(_serialize_trash_site(site))


@login_required
@require_http_methods(["POST"])
def trash_site_mark_cleaned_api(request, site_id):
    site = get_object_or_404(TrashSite, id=site_id)

    note = request.POST.get("note", "").strip()
    bags_count = _coerce_int(request.POST.get("bags_count"), default=0)
    photos = request.FILES.getlist("photos")

    proof = CleanupProof.objects.create(
        trash_site=site,
        note=note,
        bags_count=max(0, bags_count),
        created_by=request.user,
    )
    for image in photos:
        Photo.objects.create(proof=proof, image=image)

    site.status = TrashSite.Status.CLEANED
    site.cleaned_at = timezone.now()
    site.save(update_fields=["status", "cleaned_at", "updated_at"])

    return JsonResponse(_serialize_trash_site(site))


def _extract_route_coordinates(data):
    geojson = data.get("geojson")
    if geojson:
        if isinstance(geojson, str):
            geojson = json.loads(geojson)
        if geojson.get("type") != "LineString":
            raise ValueError("geojson must be a LineString")
        coords = geojson.get("coordinates", [])
    else:
        coords = data.get("coordinates", [])
        if isinstance(coords, str):
            coords = json.loads(coords)

    if not isinstance(coords, list) or len(coords) < 2:
        raise ValueError("At least 2 coordinates are required.")

    parsed = []
    for coord in coords:
        if not isinstance(coord, (list, tuple)) or len(coord) < 2:
            raise ValueError("Coordinates must be [lng, lat].")
        parsed.append((float(coord[0]), float(coord[1])))
    return parsed


@login_required
@require_http_methods(["POST"])
def route_cleanup_create_api(request):
    data = _load_payload(request)
    try:
        coords = _extract_route_coordinates(data)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return _json_error(str(exc))

    time_spent = _coerce_int(data.get("time_spent_minutes"), default=None)
    if time_spent is not None and time_spent < 0:
        return _json_error("time_spent_minutes must be non-negative.")

    route = RouteCleanup.objects.create(
        geometry=LineString(*coords, srid=4326),
        notes=str(data.get("notes", "")).strip(),
        time_spent_minutes=time_spent,
        created_by=request.user,
    )

    photos = request.FILES.getlist("photos")
    if photos:
        proof = CleanupProof.objects.create(
            route_cleanup=route,
            note=route.notes,
            bags_count=max(0, _coerce_int(data.get("bags_count"), default=0)),
            created_by=request.user,
        )
        for image in photos:
            Photo.objects.create(proof=proof, image=image)

    return JsonResponse(_serialize_route(route), status=201)


@login_required
@require_GET
def trash_site_detail_api(request, site_id):
    site = get_object_or_404(
        TrashSite.objects.select_related("created_by", "claimed_by").prefetch_related("proofs__photos", "proofs__created_by"),
        id=site_id,
    )
    return JsonResponse(_serialize_trash_site(site))


@login_required
@require_GET
def route_cleanup_detail_api(request, route_id):
    route = get_object_or_404(
        RouteCleanup.objects.select_related("created_by").prefetch_related("proofs__photos", "proofs__created_by"),
        id=route_id,
    )
    return JsonResponse(_serialize_route(route))
