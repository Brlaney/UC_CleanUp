"""Django settings for putnam_trashmap project."""

import os
from pathlib import Path

import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS", "127.0.0.1,localhost", "192.168.1.37")
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")


# Application definition

INSTALLED_APPS = [
    "django.contrib.gis",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "storages",
    "geoapp.apps.GeoappConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "geoapp.middleware.IPBanMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "putnam_trashmap.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "putnam_trashmap.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

default_database_url = (
    f"postgres://{os.getenv('POSTGRES_USER', 'putnam')}:{os.getenv('POSTGRES_PASSWORD', 'putnam')}"
    f"@{os.getenv('POSTGRES_HOST', '127.0.0.1')}:{os.getenv('POSTGRES_PORT', '5432')}"
    f"/{os.getenv('POSTGRES_DB', 'putnam_trashmap')}"
)

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DB_CONN_STRING", os.getenv("DATABASE_URL", default_database_url)),
        engine="django.contrib.gis.db.backends.postgis",
        conn_max_age=int(os.getenv("CONN_MAX_AGE", "60")),
        ssl_require=os.getenv("DATABASE_SSL_REQUIRE", "0") == "1",
    )
}


# Cache (used by django-ratelimit)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ratelimit",
    }
}

_redis_url = os.getenv("REDIS_URL")
if _redis_url:
    CACHES["default"] = {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": _redis_url,
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "America/Chicago")

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STATICFILES_BACKEND = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if not DEBUG
    else "django.contrib.staticfiles.storage.StaticFilesStorage"
)

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

USE_S3_MEDIA = os.getenv("USE_S3_MEDIA", "0") == "1"
if USE_S3_MEDIA:
    AWS_ACCESS_KEY_ID = os.getenv("CF_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.getenv("CF_SECRET_ACCESS_KEY", "")
    AWS_STORAGE_BUCKET_NAME = os.getenv("CF_BUCKET_NAME", "")
    AWS_S3_REGION_NAME = "auto"
    AWS_S3_ENDPOINT_URL = os.getenv("CF_S3_ENDPOINT_URL", "")
    AWS_S3_CUSTOM_DOMAIN = os.getenv("CF_S3_CUSTOM_DOMAIN", "")
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_FILE_OVERWRITE = False
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": AWS_STORAGE_BUCKET_NAME,
                "default_acl": None,
                "endpoint_url": AWS_S3_ENDPOINT_URL or None,
                "region_name": AWS_S3_REGION_NAME or None,
                "custom_domain": AWS_S3_CUSTOM_DOMAIN or None,
                "location": "media",
            },
        },
        "staticfiles": {
            "BACKEND": STATICFILES_BACKEND,
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": STATICFILES_BACKEND,
        },
    }

# Required by OSM tile usage policy — send origin on cross-origin tile requests.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "1") == "1"
    SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "1") == "1"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
else:
    SECURE_SSL_REDIRECT = False

if not DEBUG and SECRET_KEY == "dev-only-change-me":
    raise RuntimeError("SECRET_KEY must be set in production.")

if not DEBUG and not ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS must be set in production.")

if not DEBUG and USE_S3_MEDIA:
    required_storage_values = {
        "CF_ACCESS_KEY_ID": os.getenv("CF_ACCESS_KEY_ID", ""),
        "CF_SECRET_ACCESS_KEY": os.getenv("CF_SECRET_ACCESS_KEY", ""),
        "CF_BUCKET_NAME": os.getenv("CF_BUCKET_NAME", ""),
        "CF_S3_ENDPOINT_URL": os.getenv("CF_S3_ENDPOINT_URL", ""),
    }
    missing_storage_values = [key for key, value in required_storage_values.items() if not value]
    if missing_storage_values:
        raise RuntimeError(f"Missing required S3/R2 settings: {', '.join(missing_storage_values)}")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
        "simple": {
            "format": "%(levelname)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if not DEBUG else "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
