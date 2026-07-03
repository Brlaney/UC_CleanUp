from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("geoapp", "0013_alter_profile_role_alter_teammembership_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="trashsite",
            name="hazard_types",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
