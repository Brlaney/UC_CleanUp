from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("geoapp", "0003_district_photo_photo_type_trashsite_area_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserMapPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("default_county", models.CharField(blank=True, max_length=100)),
                ("visible_district_slugs", models.JSONField(default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="map_preference",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
