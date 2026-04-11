import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('geoapp', '0005_preserve_user_data_on_delete'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # TrashSite: verification fields
        migrations.AddField(
            model_name='trashsite',
            name='verified_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='verifications',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='trashsite',
            name='verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trashsite',
            name='verification_note',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='trashsite',
            name='work_order',
            field=models.CharField(blank=True, max_length=100),
        ),
        # Profile: public_profile for leaderboard opt-in
        migrations.AddField(
            model_name='profile',
            name='public_profile',
            field=models.BooleanField(default=False),
        ),
    ]
