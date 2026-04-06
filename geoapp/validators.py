from django.core.exceptions import ValidationError

MAX_PHOTO_COUNT = 5
MAX_PHOTO_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


def validate_photo_uploads(files, max_count=MAX_PHOTO_COUNT):
    """Validate a list of uploaded photo files for count, size, and MIME type."""
    if len(files) > max_count:
        raise ValidationError(f"Maximum {max_count} photos allowed per submission.")
    for f in files:
        if f.size > MAX_PHOTO_SIZE_BYTES:
            raise ValidationError(f"Each photo must be under 10 MB. '{f.name}' is too large.")
        if f.content_type not in ALLOWED_IMAGE_TYPES:
            raise ValidationError(
                f"Unsupported image type '{f.content_type}' for '{f.name}'. "
                f"Allowed: JPEG, PNG, WebP, HEIC."
            )
