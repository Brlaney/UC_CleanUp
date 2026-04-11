from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("geoapp", "0011_trashsite_chronic_badge_challenge"),
    ]

    operations = [
        migrations.AddField(
            model_name="usermappreference",
            name="default_counties",
            field=models.JSONField(default=list),
        ),
    ]
