import os

# Provide an explicit test key before importing production settings, which now
# refuse to boot without a SECRET_KEY outside a dev context (#685). Using
# setdefault lets an explicit env var still win.
os.environ.setdefault("SECRET_KEY", "test-insecure-key")

from config.settings import *  # noqa: E402, F401, F403

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
