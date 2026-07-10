"""Regression tests for security-hardening settings (#684, #685, #688).

These exercise the settings module under controlled environment variables, so
each case runs config.settings fresh in a subprocess rather than mutating the
already-imported module.
"""
import os
import subprocess
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_settings(env):
    """Import config.settings in a clean subprocess with the given env.

    Returns (returncode, stdout, stderr). The child prints requested settings
    values to stdout as `KEY=repr(value)` lines when import succeeds.
    """
    probe = (
        "import config.settings as s\n"
        "for k in ['SECRET_KEY','SESSION_COOKIE_SECURE','CSRF_COOKIE_SECURE',"
        "'SECURE_CONTENT_TYPE_NOSNIFF','CSRF_COOKIE_HTTPONLY']:\n"
        "    print(f'{k}={getattr(s, k)!r}')\n"
        "print('HSTS=' + repr(getattr(s, 'SECURE_HSTS_SECONDS', None)))\n"
        "print('HSTS_SUB=' + repr(getattr(s, 'SECURE_HSTS_INCLUDE_SUBDOMAINS', None)))\n"
        "print('HSTS_PRELOAD=' + repr(getattr(s, 'SECURE_HSTS_PRELOAD', None)))\n"
    )
    full_env = {"PATH": os.environ.get("PATH", "")}
    full_env.update(env)
    return subprocess.run(
        [sys.executable, "-c", probe],
        cwd=BACKEND_DIR,
        env=full_env,
        capture_output=True,
        text=True,
    )


def _parse(stdout):
    return dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)


# ── #685: SECRET_KEY guard ───────────────────────────────────────────────────


def test_missing_secret_key_in_production_raises():
    result = _run_settings({"DEBUG": "False", "DEV_AUTO_LOGIN": "False"})
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "SECRET_KEY" in result.stderr


def test_missing_secret_key_in_debug_uses_placeholder():
    result = _run_settings({"DEBUG": "True", "DEV_AUTO_LOGIN": "False"})
    assert result.returncode == 0, result.stderr
    values = _parse(result.stdout)
    assert values["SECRET_KEY"] == "'dev-insecure-key'"


def test_missing_secret_key_with_dev_auto_login_uses_placeholder():
    result = _run_settings({"DEBUG": "False", "DEV_AUTO_LOGIN": "True"})
    assert result.returncode == 0, result.stderr
    values = _parse(result.stdout)
    assert values["SECRET_KEY"] == "'dev-insecure-key'"


def test_secret_key_from_env_used_verbatim():
    result = _run_settings(
        {"DEBUG": "False", "DEV_AUTO_LOGIN": "False", "SECRET_KEY": "real-production-key"}
    )
    assert result.returncode == 0, result.stderr
    values = _parse(result.stdout)
    assert values["SECRET_KEY"] == "'real-production-key'"


# ── #688: transport-security settings ────────────────────────────────────────


def test_production_transport_security_enabled():
    result = _run_settings(
        {"DEBUG": "False", "DEV_AUTO_LOGIN": "False", "SECRET_KEY": "k"}
    )
    assert result.returncode == 0, result.stderr
    values = _parse(result.stdout)
    assert values["SESSION_COOKIE_SECURE"] == "True"
    assert values["CSRF_COOKIE_SECURE"] == "True"
    assert values["SECURE_CONTENT_TYPE_NOSNIFF"] == "True"
    assert values["HSTS"] == "31536000"
    assert values["HSTS_SUB"] == "True"
    assert values["HSTS_PRELOAD"] == "True"
    # SPA double-submit pattern relies on JS reading the CSRF cookie.
    assert values["CSRF_COOKIE_HTTPONLY"] == "False"


def test_dev_context_does_not_force_secure_cookies():
    # docker-compose dev sets DEV_AUTO_LOGIN (not DEBUG) and serves plain HTTP.
    result = _run_settings({"DEBUG": "False", "DEV_AUTO_LOGIN": "True"})
    assert result.returncode == 0, result.stderr
    values = _parse(result.stdout)
    assert values["SESSION_COOKIE_SECURE"] == "False"
    assert values["CSRF_COOKIE_SECURE"] == "False"
    assert values["HSTS"] == "None"
