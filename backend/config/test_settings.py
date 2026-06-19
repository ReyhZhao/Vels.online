from config.settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Use an isolated in-memory cache for tests. Inheriting the production CACHES
# points tests at the shared valkey instance (REDIS_URL is set in Docker) — the
# same database the live dev backend uses — so cache keys mutate underneath the
# suite mid-run and make cache-dependent assertions flaky. LocMemCache gives
# each test process its own deterministic, isolated cache.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
