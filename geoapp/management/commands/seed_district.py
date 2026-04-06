import json

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand, CommandError

from geoapp.models import District


class Command(BaseCommand):
    help = "Load a district boundary from a GeoJSON file into the District table."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to GeoJSON file")
        parser.add_argument("--name", required=True, help="District display name")
        parser.add_argument("--slug", required=True, help="District URL slug (unique)")
        parser.add_argument("--description", default="", help="Optional description")

    def handle(self, *args, **options):
        filepath = options["file"]
        name = options["name"]
        slug = options["slug"]
        description = options["description"]

        try:
            with open(filepath, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot read GeoJSON file: {exc}")

        features = data.get("features", [])
        if not features:
            raise CommandError("GeoJSON file contains no features.")

        geom_data = features[0].get("geometry")
        if not geom_data:
            raise CommandError("First feature has no geometry.")

        geom = GEOSGeometry(json.dumps(geom_data), srid=4326)

        if isinstance(geom, Polygon):
            geom = MultiPolygon(geom, srid=4326)
        elif not isinstance(geom, MultiPolygon):
            raise CommandError(f"Expected Polygon or MultiPolygon, got {geom.geom_type}.")

        district, created = District.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "geometry": geom,
                "description": description,
                "active": True,
            },
        )

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} district '{district.name}' (slug={district.slug})"))
