from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("geoapp", "0009_push_subscription"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduledJobLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_name", models.CharField(db_index=True, max_length=100, unique=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("last_status", models.CharField(default="never", max_length=20)),
                ("last_error", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
