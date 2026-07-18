import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "12345")

ONCALL_ROUTING = os.environ.get("ONCALL_ROUTING", "always")

DEBUG = os.environ.get("DEBUG", "False") == "True"

# Local-dev only: skip interactive login and auto-authenticate as the admin
# superuser (see config.middleware.DevAutoLoginMiddleware). Set ONLY in
# docker-compose.yaml — never in the deployment/ Helm manifests. Intentionally
# independent of DEBUG, since prod also runs with DEBUG=True.
DEV_AUTO_LOGIN = os.environ.get("DEV_AUTO_LOGIN", "False") == "True"

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
    # Operational observability (ADR-0019). Tenant-agnostic platform metrics,
    # scraped on a dedicated port that is not routed by the public Ingress.
    "django_prometheus",
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
    "adrf",
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
    "correlations",
    "hunts",
    "attackmap",
    "core",
    "django_celery_results",
    "django_celery_beat",
    "celery_tasks",
    "oncall",
    "partners",
]

SITE_ID = 1

MIDDLEWARE = [
    # PrometheusBeforeMiddleware must be first and PrometheusAfterMiddleware last
    # so request latency/count metrics span the whole middleware stack (ADR-0019).
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "config.middleware.ForceHttpsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Local-dev auto-login (no-op unless DEV_AUTO_LOGIN=True; see middleware).
    # Must follow Session + Authentication middleware so request.session/user exist.
    "config.middleware.DevAutoLoginMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
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
ASGI_APPLICATION = "config.asgi.application"

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

# Live Attack Map (PRD #594): global severity floor feeding the snapshot producer.
# Default 3 — deliberately low for arc density while the map is young; raise toward 7
# later. A runtime cache override (attackmap.config.set_severity_floor) wins over this.
ATTACK_MAP_SEVERITY_FLOOR = int(os.environ.get("ATTACK_MAP_SEVERITY_FLOOR", "3"))

UPTIMEROBOT_API_KEY = os.environ.get("UPTIMEROBOT_API_KEY", "")

ABUSEIPDB_API_KEY = os.environ.get("ABUSEIPDB_API_KEY", None)
VIRUSTOTAL_API_KEY = os.environ.get("VIRUSTOTAL_API_KEY", None)

CELERY_BROKER_URL = _REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# Emit task-sent/-received events so the off-the-shelf celery-exporter can report
# throughput, failures, retries and queue depth without instrumenting worker code
# (ADR-0019). The exporter consumes these events from the Valkey broker.
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True

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
        # Service-account-aware token auth (#696): enforces the per-account source-IP
        # allowlist and records last-used time/IP. A drop-in for the stock class.
        "security.authentication.ServiceAccountTokenAuthentication",
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
# Gemini 3 is required for the assistant agentic loop (ADR-0011): only Gemini 3
# can combine native google_search grounding with custom function tools in a
# single request. Overridable via env.
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-3-flash")
EXCEPTION_LLM_PROVIDER = os.environ.get(
    "EXCEPTION_LLM_PROVIDER",
    "exceptions.llm.gemini.GeminiFlashProvider",
)
TRIAGE_LLM_PROVIDER = os.environ.get(
    "TRIAGE_LLM_PROVIDER",
    "incidents.llm.gemini.GeminiTriageProvider",
)
# The batched Triage Lesson distillation sweep (ADR-0030) — a low-volume reasoning job,
# so it can point at a stronger model than per-alert classify. Defaults to the triage
# provider, so behaviour is unchanged until this is set explicitly.
DISTILL_LLM_PROVIDER = os.environ.get(
    "DISTILL_LLM_PROVIDER",
    TRIAGE_LLM_PROVIDER,
)
CORRELATION_LLM_PROVIDER = os.environ.get(
    "CORRELATION_LLM_PROVIDER",
    "correlations.llm.gemini.GeminiDraftProvider",
)
INCIDENT_ASSISTANT_LLM_PROVIDER = os.environ.get(
    "INCIDENT_ASSISTANT_LLM_PROVIDER",
    "incidents.llm.gemini.GeminiTriageProvider",
)
CLOSURE_LLM_PROVIDER = os.environ.get(
    "CLOSURE_LLM_PROVIDER",
    "incidents.llm.gemini.GeminiTriageProvider",
)
GROUNDING_WINDOW_DAYS = int(os.environ.get("GROUNDING_WINDOW_DAYS", "30"))
GROUNDING_VALUE_CAP   = int(os.environ.get("GROUNDING_VALUE_CAP", "50"))
GROUNDING_SAMPLE_CAP  = int(os.environ.get("GROUNDING_SAMPLE_CAP", "15"))

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "mistral")
OLLAMA_API_KEY  = os.environ.get("OLLAMA_API_KEY", "")
# Per-call HTTP timeout for every Ollama client (chat / web_search) so a hung endpoint
# raises rather than blocking a gunicorn worker forever. Must stay below the gunicorn
# --timeout (see backend/Dockerfile) so the worker is never SIGABRT-killed mid-call.
OLLAMA_TIMEOUT_S = float(os.environ.get("OLLAMA_TIMEOUT_S", "60"))

# Embedding config for the #657 semantic-precedent-recall measurement (a background research
# job — measure_semantic_precedent_recall — NOT a production serving path; see ADR-0030).
# Defaults to Ollama Cloud to match the production triage provider; set to "gemini" to run
# the measurement against Gemini's embedding endpoint instead.
EMBED_MEASURE_PROVIDER = os.environ.get("EMBED_MEASURE_PROVIDER", "ollama")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "embeddinggemma")
GEMINI_EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "text-embedding-004")

# Assistant agentic tool-calling loop (ADR-0011). Caps bound a single turn.
# ASSISTANT_LOOP_DEADLINE_S (research) + pass-1 + pass-2 (each ≤ OLLAMA_TIMEOUT_S) must
# stay comfortably under the gunicorn --timeout so the loop self-limits before gunicorn.
ASSISTANT_LOOP_MAX_ITERATIONS = int(os.environ.get("ASSISTANT_LOOP_MAX_ITERATIONS", "5"))
ASSISTANT_TOOL_TIMEOUT_S      = float(os.environ.get("ASSISTANT_TOOL_TIMEOUT_S", "10"))
ASSISTANT_LOOP_DEADLINE_S     = float(os.environ.get("ASSISTANT_LOOP_DEADLINE_S", "60"))
ASSISTANT_MAX_AUTO_ACTIONS    = int(os.environ.get("ASSISTANT_MAX_AUTO_ACTIONS", "8"))
# Web search is available when an Ollama Cloud key is configured (or Gemini grounding).
ASSISTANT_WEB_SEARCH_ENABLED  = os.environ.get("ASSISTANT_WEB_SEARCH_ENABLED", "1") == "1"

# Threat Hunting loop caps (ADR-0016). Relaxed vs the incident assistant since a hunt
# turn runs as a Celery background job (no proxy-timeout pressure).
HUNT_LOOP_MAX_ITERATIONS = int(os.environ.get("HUNT_LOOP_MAX_ITERATIONS", "15"))
HUNT_TOOL_TIMEOUT_S      = float(os.environ.get("HUNT_TOOL_TIMEOUT_S", "15"))
HUNT_LOOP_DEADLINE_S     = float(os.environ.get("HUNT_LOOP_DEADLINE_S", "300"))
HUNT_MAX_AUTO_ACTIONS    = int(os.environ.get("HUNT_MAX_AUTO_ACTIONS", "8"))

INCIDENT_SLA_TARGETS = {
    "critical": {"response_seconds": 15 * 60,       "resolve_seconds": 4 * 3600},
    "high":     {"response_seconds": 1 * 3600,       "resolve_seconds": 24 * 3600},
    "medium":   {"response_seconds": 4 * 3600,       "resolve_seconds": 3 * 24 * 3600},
    "low":      {"response_seconds": 24 * 3600,      "resolve_seconds": 7 * 24 * 3600},
}
