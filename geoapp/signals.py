from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CleanupEvent, CleanupProof, Profile, Team, TrashSite


@receiver(post_save, sender=get_user_model())
def ensure_profile_for_user(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=CleanupProof)
def on_proof_saved(sender, instance, created, **kwargs):
    if created and instance.created_by_id:
        from .services import check_and_award_badges
        try:
            check_and_award_badges(instance.created_by)
        except Exception:
            pass


@receiver(post_save, sender=TrashSite)
def on_site_saved(sender, instance, created, **kwargs):
    if created and instance.created_by_id and instance.hazard_flag:
        from .services import check_and_award_badges
        try:
            check_and_award_badges(instance.created_by)
        except Exception:
            pass


@receiver(post_save, sender=Team)
def on_team_saved(sender, instance, created, **kwargs):
    if created and instance.leader_id:
        from .services import check_and_award_badges
        try:
            check_and_award_badges(instance.leader)
        except Exception:
            pass


@receiver(post_save, sender=CleanupEvent)
def on_event_saved(sender, instance, created, **kwargs):
    if created and instance.organizer_id:
        from .services import check_and_award_badges
        try:
            check_and_award_badges(instance.organizer)
        except Exception:
            pass
