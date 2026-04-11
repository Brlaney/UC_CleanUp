"""
fetch_districts
===============
Fetches all Putnam County commission district boundaries from the TNMap
ArcGIS REST service, dissolves the VTD polygons per CCD (commission district
number), writes one GeoJSON file per district to static/data/, and upserts
each into the District table.

Usage:
    python manage.py fetch_districts
"""

import json
import urllib.request
from collections import defaultdict

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand, CommandError

from geoapp.models import District

TNMAP_URL = (
    "https://tnmap.tn.gov/arcgis/rest/services/"
    "ADMINISTRATIVE_BOUNDARIES/VOTING_DISTRICTS/MapServer/0/query"
    "?where=COUNTY%3D141"
    "&outFields=NAME%2CDISTRICT%2CCCD%2CVTD%2CCOUNTY"
    "&returnGeometry=true"
    "&f=geojson"
)

GEOJSON_DIR = "static/data"


def _to_multipolygon(geom):
    """Ensure a GEOSGeometry is a MultiPolygon."""
    if isinstance(geom, Polygon):
        return MultiPolygon(geom, srid=4326)
    if isinstance(geom, MultiPolygon):
        return geom
    # GeometryCollection or other — extract polygons
    polys = []
    for g in geom:
        if isinstance(g, Polygon):
            polys.append(g)
        elif isinstance(g, MultiPolygon):
            polys.extend(g)
    if not polys:
        raise CommandError(f"Could not extract polygons from {geom.geom_type}")
    return MultiPolygon(*polys, srid=4326)


class Command(BaseCommand):
    help = "Fetch all Putnam County commission districts from TNMap and seed the District table."

    def handle(self, *args, **options):
        self.stdout.write("Fetching district boundaries from TNMap...")
        try:
            with urllib.request.urlopen(TNMAP_URL, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except Exception as exc:
            raise CommandError(f"Failed to fetch TNMap data: {exc}")

        features = data.get("features", [])
        if not features:
            raise CommandError("TNMap returned no features.")

        self.stdout.write(f"  Got {len(features)} VTD features — grouping by CCD...")

        # Group VTD features by CCD (commission district number)
        by_ccd = defaultdict(list)
        for f in features:
            ccd = f["properties"].get("CCD")
            if ccd is not None:
                by_ccd[int(ccd)].append(f)

        self.stdout.write(f"  Found {len(by_ccd)} commission districts: {sorted(by_ccd)}")

        for ccd in sorted(by_ccd):
            vtds = by_ccd[ccd]
            name = f"District {ccd}"
            slug = f"district-{ccd}"

            # Dissolve all VTD polygons for this CCD into one MultiPolygon
            dissolved = None
            for vtd in vtds:
                geom_json = json.dumps(vtd["geometry"])
                geom = GEOSGeometry(geom_json, srid=4326)
                dissolved = geom if dissolved is None else dissolved.union(geom)

            dissolved = _to_multipolygon(dissolved)

            # Write GeoJSON file
            geojson_path = f"{GEOJSON_DIR}/{slug}_boundary.geojson"
            feature_collection = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {"name": name, "slug": slug, "ccd": ccd},
                    "geometry": json.loads(dissolved.geojson),
                }],
            }
            with open(geojson_path, "w") as fh:
                json.dump(feature_collection, fh)

            # Upsert District record
            district, created = District.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "geometry": dissolved,
                    "active": True,
                    "description": f"Putnam County Commission District {ccd}",
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(f"  {action} '{name}' ({len(vtds)} VTDs merged)")
            )

        self.stdout.write(self.style.SUCCESS(
            f"Done — {len(by_ccd)} commission districts seeded."
        ))
