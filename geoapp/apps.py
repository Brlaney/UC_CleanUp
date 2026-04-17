from django.apps import AppConfig


class GeoappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "geoapp"

    def ready(self):
        from . import signals  # noqa: F401
        from django.db.models.signals import post_migrate
        post_migrate.connect(_seed_badges, sender=self)


def _seed_badges(sender, **kwargs):
    """Seed built-in badge records after migrations run (idempotent)."""
    try:
        from .services import _ensure_badges
        _ensure_badges()
    except Exception:
        pass
