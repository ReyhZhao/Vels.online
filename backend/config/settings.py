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
    "rest_framework.authtoken",
    "drf_spectacular",
    "django_filters",
    "api",
    "blog",
    "status",
    "security",
    "incidents",
    "exceptions",
    "notifications",
    "feedback",
    "ingress",
    "signups",
    "automations",
    "contacts",
    "inbound_mail",
    "alerts",
    "core",
    "django_celery_results",
    "django_celery_beat",
    "celery_tasks",
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

ABUSEIPDB_API_KEY = os.environ.get("ABUSEIPDB_API_KEY", None)
VIRUSTOTAL_API_KEY = os.environ.get("VIRUSTOTAL_API_KEY", None)

CELERY_BROKER_URL = _REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ── Email ──────────────────────────────────────────────────────────────────────
_email_ssl_no_verify = os.environ.get("EMAIL_SSL_NO_VERIFY", "False") == "True"
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "config.email_backend.UnverifiedSSLEmailBackend" if _email_ssl_no_verify
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST          = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT          = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS       = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_USE_SSL       = os.environ.get("EMAIL_USE_SSL", "False") == "True"
EMAIL_HOST_USER     = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL  = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@vels.online")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
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

_authentik_url = os.environ.get("AUTHENTIK_SERVER_URL", "")
SOCIALACCOUNT_PROVIDERS = {
    "openid_connect": {
        "APPS": [
            {
                "provider_id": "authentik",
                "name": "Authentik",
                "client_id": os.environ.get("AUTHENTIK_CLIENT_ID", ""),
                "secret": os.environ.get("AUTHENTIK_CLIENT_SECRET", ""),
                "settings": {
                    "server_url": _authentik_url,
                },
            }
        ]
        if _authentik_url
        else []
    }
}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")

BUNKERWEB_API_URL = os.environ.get("BUNKERWEB_API_URL", "")
BUNKERWEB_API_TOKEN = os.environ.get("BUNKERWEB_API_TOKEN", "")
BUNKERWEB_PUBLIC_IP = os.environ.get("BUNKERWEB_PUBLIC_IP", "")
BUNKERWEB_PUBLIC_FQDN = os.environ.get("BUNKERWEB_PUBLIC_FQDN", "")

# VAPID keys for web push notifications.
# Generate once per deployment:
#   python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print('Public:', v.public_key); print('Private:', v.private_key)"
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@vels.online")

AUTHENTIK_API_TOKEN = os.environ.get("AUTHENTIK_API_TOKEN", "")
AUTHENTIK_API_URL = os.environ.get("AUTHENTIK_API_URL", "")
AUTHENTIK_ENROLLMENT_FLOW_SLUG = os.environ.get("AUTHENTIK_ENROLLMENT_FLOW_SLUG", "")

TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://vels.online")

WAZUH_RULES_GITHUB_TOKEN = os.environ.get("WAZUH_RULES_GITHUB_TOKEN", "")

SEMAPHORE_URL = os.environ.get("SEMAPHORE_URL", "")
SEMAPHORE_API_TOKEN = os.environ.get("SEMAPHORE_API_TOKEN", "")
SEMAPHORE_PROJECT_ID = int(os.environ.get("SEMAPHORE_PROJECT_ID", "0"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
EXCEPTION_LLM_PROVIDER = os.environ.get(
    "EXCEPTION_LLM_PROVIDER",
    "exceptions.llm.gemini.GeminiFlashProvider",
)
TRIAGE_LLM_PROVIDER = os.environ.get(
    "TRIAGE_LLM_PROVIDER",
    "incidents.llm.gemini.GeminiTriageProvider",
)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "mistral")
OLLAMA_API_KEY  = os.environ.get("OLLAMA_API_KEY", "")

INCIDENT_SLA_TARGETS = {
    "critical": {"response_seconds": 15 * 60,       "resolve_seconds": 4 * 3600},
    "high":     {"response_seconds": 1 * 3600,       "resolve_seconds": 24 * 3600},
    "medium":   {"response_seconds": 4 * 3600,       "resolve_seconds": 3 * 24 * 3600},
    "low":      {"response_seconds": 24 * 3600,      "resolve_seconds": 7 * 24 * 3600},
}
