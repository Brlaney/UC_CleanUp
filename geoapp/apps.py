from django.apps import AppConfig


class GeoappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "geoapp"

    def ready(self):
        from . import signals  # noqa: F401
        # Seed built-in badges (idempotent, no-ops if already present)
        try:
            from .services import _ensure_badges
            _ensure_badges()
        except Exception:
            pass
