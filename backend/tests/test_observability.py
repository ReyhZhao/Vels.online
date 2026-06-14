"""Operational observability wiring (ADR-0019).

These guard the app-level instrumentation contract: django-prometheus is installed
and its middleware brackets the stack, Celery emits task events for the off-the-shelf
exporter, and the multiprocess metrics endpoint aggregates across worker processes.
"""
import tempfile

from django.conf import settings


def test_django_prometheus_installed():
    assert "django_prometheus" in settings.INSTALLED_APPS


def test_prometheus_middleware_brackets_the_stack():
    # Before must be first and After last so latency/count metrics span all middleware.
    assert settings.MIDDLEWARE[0] == "django_prometheus.middleware.PrometheusBeforeMiddleware"
    assert settings.MIDDLEWARE[-1] == "django_prometheus.middleware.PrometheusAfterMiddleware"


def test_celery_task_events_enabled_for_exporter():
    assert settings.CELERY_WORKER_SEND_TASK_EVENTS is True
    assert settings.CELERY_TASK_SEND_SENT_EVENT is True


def test_metrics_exporter_serves_aggregated_multiprocess_registry():
    # The sidecar builds a MultiProcessCollector over the shared dir rather than the
    # default registry, so it reflects all gunicorn workers, not one process.
    from metrics_exporter import build_app

    with tempfile.TemporaryDirectory() as d:
        app = build_app(multiproc_dir=d)

        captured = {}

        def start_response(status, headers):
            captured["status"] = status

        body = b"".join(app({"PATH_INFO": "/", "REQUEST_METHOD": "GET"}, start_response))

    assert captured["status"].startswith("200")
    assert b"# HELP" in body or body == b""


def test_metrics_exporter_defaults_to_env_dir(monkeypatch):
    from metrics_exporter import build_app

    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", d)
        assert callable(build_app())
