import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('geoapp', '0007_cleanupevent_eventrsvp'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('slug', models.SlugField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
                ('org_type', models.CharField(
                    choices=[('SCHOOL', 'School'), ('CIVIC', 'Civic Group'), ('CHURCH', 'Church'), ('SCOUT', 'Scout Troop'), ('OTHER', 'Other')],
                    default='OTHER', max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('district', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='teams', to='geoapp.district',
                )),
                ('leader', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='led_teams', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='TeamMembership',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[('LEADER', 'Leader'), ('MEMBER', 'Member')],
                    default='MEMBER', max_length=10,
                )),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('team', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='memberships', to='geoapp.team',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='team_memberships', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['joined_at'],
                'unique_together': {('user', 'team')},
            },
        ),
        migrations.AddField(
            model_name='trashsite',
            name='team',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='trash_sites', to='geoapp.team',
            ),
        ),
        migrations.AddField(
            model_name='cleanupproof',
            name='team',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cleanup_proofs', to='geoapp.team',
            ),
        ),
    ]
