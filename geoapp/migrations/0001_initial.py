# Generated manually for trash mapping MVP.

import uuid

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.contrib.postgres.operations import CreateExtension
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        CreateExtension("postgis"),
        migrations.CreateModel(
            name="RouteCleanup",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("geometry", django.contrib.gis.db.models.fields.LineStringField(geography=True, srid=4326)),
                ("status", models.CharField(choices=[("LOGGED", "Logged"), ("VERIFIED", "Verified")], default="LOGGED", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("distance_miles", models.FloatField(default=0.0)),
                ("time_spent_minutes", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="routes_created", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="TrashSite",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("IN_PROGRESS", "In Progress"),
                            ("CLEANED", "Cleaned"),
                            ("INVALID", "Invalid"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("location", django.contrib.gis.db.models.fields.PointField(geography=True, srid=4326)),
                ("title", models.CharField(blank=True, max_length=255)),
                ("description", models.TextField(blank=True)),
                ("severity", models.CharField(blank=True, choices=[("LIGHT", "Light"), ("MEDIUM", "Medium"), ("HEAVY", "Heavy")], max_length=10)),
                ("hazard_flag", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cleaned_at", models.DateTimeField(blank=True, null=True)),
                (
                    "claimed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="trash_sites_claimed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trash_sites_created", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="CleanupProof",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("note", models.TextField(blank=True)),
                ("bags_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="proofs_created", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "route_cleanup",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="proofs", to="geoapp.routecleanup"),
                ),
                (
                    "trash_site",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="proofs", to="geoapp.trashsite"),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Photo",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("image", models.ImageField(upload_to="proof_photos/%Y/%m/%d")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("proof", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="geoapp.cleanupproof")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
