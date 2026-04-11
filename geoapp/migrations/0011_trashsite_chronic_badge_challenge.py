import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("geoapp", "0010_scheduledjoblog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # chronic_site flag on TrashSite
        migrations.AddField(
            model_name="trashsite",
            name="chronic_site",
            field=models.BooleanField(db_index=True, default=False),
        ),
        # Badge
        migrations.CreateModel(
            name="Badge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("description", models.CharField(max_length=255)),
                ("icon", models.CharField(max_length=50)),
            ],
            options={"ordering": ["slug"]},
        ),
        # UserBadge
        migrations.CreateModel(
            name="UserBadge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("awarded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "badge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="user_badges",
                        to="geoapp.badge",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="badges",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["awarded_at"], "unique_together": {("user", "badge")}},
        ),
        # Challenge
        migrations.CreateModel(
            name="Challenge",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                ("start_date", models.DateField(db_index=True)),
                ("end_date", models.DateField(db_index=True)),
                ("bag_goal", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[("UPCOMING", "Upcoming"), ("ACTIVE", "Active"), ("COMPLETED", "Completed")],
                        db_index=True,
                        default="UPCOMING",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-start_date"]},
        ),
    ]
