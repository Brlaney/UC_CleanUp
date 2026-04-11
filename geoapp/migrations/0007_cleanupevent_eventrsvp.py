import django.contrib.gis.db.models.fields
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('geoapp', '0006_phase2_verification_leaderboard'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CleanupEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('location', django.contrib.gis.db.models.fields.PointField(geography=True, srid=4326)),
                ('event_date', models.DateTimeField(db_index=True)),
                ('status', models.CharField(
                    choices=[('SCHEDULED', 'Scheduled'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')],
                    db_index=True, default='SCHEDULED', max_length=20,
                )),
                ('max_attendees', models.PositiveIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('district', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='events', to='geoapp.district',
                )),
                ('organizer', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='organized_events', to=settings.AUTH_USER_MODEL,
                )),
                ('trash_site', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='events', to='geoapp.trashsite',
                )),
            ],
            options={'ordering': ['event_date']},
        ),
        migrations.CreateModel(
            name='EventRSVP',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=100)),
                ('email', models.EmailField(blank=True)),
                ('rsvp_at', models.DateTimeField(auto_now_add=True)),
                ('event', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rsvps', to='geoapp.cleanupevent',
                )),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='event_rsvps', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['rsvp_at'],
                'unique_together': {('event', 'user')},
            },
        ),
    ]
