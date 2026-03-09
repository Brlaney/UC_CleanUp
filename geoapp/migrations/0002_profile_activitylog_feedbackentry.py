# Generated manually for private beta and production-readiness features.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_profiles_for_existing_users(apps, schema_editor):
    profile_model = apps.get_model("geoapp", "Profile")
    user_model = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    for user in user_model.objects.all():
        profile_model.objects.get_or_create(user=user)


class Migration(migrations.Migration):
    dependencies = [
        ("geoapp", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FeedbackEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("feedback_type", models.CharField(choices=[("BUG", "Bug"), ("REQUEST", "Request"), ("GENERAL", "General")], db_index=True, default="GENERAL", max_length=20)),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("ACKNOWLEDGED", "Acknowledged"), ("CLOSED", "Closed")], db_index=True, default="OPEN", max_length=20)),
                ("message", models.TextField()),
                ("page_url", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feedback_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Profile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("MEMBER", "Member"), ("ADMIN", "Admin")], db_index=True, default="MEMBER", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["user__username"]},
        ),
        migrations.CreateModel(
            name="ActivityLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("activity_type", models.CharField(choices=[("TRASH_REPORTED", "Trash Reported"), ("TRASH_UPDATED", "Trash Updated"), ("TRASH_CLEANED", "Trash Cleaned"), ("ROUTE_LOGGED", "Route Logged"), ("PROOF_ADDED", "Proof Added")], db_index=True, max_length=30)),
                ("summary", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activity_logs", to=settings.AUTH_USER_MODEL)),
                ("proof", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="activity_logs", to="geoapp.cleanupproof")),
                ("route_cleanup", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="activity_logs", to="geoapp.routecleanup")),
                ("trash_site", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="activity_logs", to="geoapp.trashsite")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.RunPython(create_profiles_for_existing_users, migrations.RunPython.noop),
    ]
