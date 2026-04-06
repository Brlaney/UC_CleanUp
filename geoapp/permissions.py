from .models import Profile, TrashSite


def is_admin(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.role == Profile.Role.ADMIN)


def can_edit_trash_site(user, site):
    return bool(user and user.is_authenticated and (is_admin(user) or site.created_by_id == user.id))


def can_mark_cleaned(user, site):
    return bool(user and user.is_authenticated and site.status != TrashSite.Status.INVALID)


def can_set_invalid_status(user):
    return is_admin(user)


def can_submit_report(user):
    return bool(user and user.is_authenticated)


def can_submit_cleanup(user, site):
    return bool(user and user.is_authenticated and site.status != TrashSite.Status.INVALID)


def can_view_feedback_admin(user):
    return is_admin(user)
