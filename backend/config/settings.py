import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "12345")

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")

CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"

CSP_FORM_ACTION = (
    "'self'",
    "https://vels.online",
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.openid_connect",
    "rest_framework",
    "drf_spectacular",
    "api",
    "blog",
    "status",
    "security",
]

SITE_ID = 1

MIDDLEWARE = [
    "config.middleware.ForceHttpsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

_REDIS_URL = os.environ.get("REDIS_URL", "")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": _REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
    if _REDIS_URL
    else {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

UPTIMEROBOT_API_KEY = os.environ.get("UPTIMEROBOT_API_KEY", "")

CELERY_BROKER_URL = _REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = _REDIS_URL or "cache+memory://"
CELERY_BEAT_SCHEDULE = {
    "snapshot-vulnerabilities-daily": {
        "task": "security.tasks.snapshot_vulnerabilities",
        "schedule": 86400,  # every 24 hours
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Vels Online API",
    "DESCRIPTION": "API for Vels Online services.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_REDIRECT_URL = "/login-redirect/"
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True

SOCIALACCOUNT_PROVIDERS = {
    "openid_connect": {
        "APPS": [
            {
                "provider_id": "authentik",
                "name": "Authentik",
                "client_id": os.environ.get("AUTHENTIK_CLIENT_ID", ""),
                "secret": os.environ.get("AUTHENTIK_CLIENT_SECRET", ""),
                "settings": {
                    "server_url": os.environ.get("AUTHENTIK_SERVER_URL", ""),
                },
            }
        ]
    }
}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
