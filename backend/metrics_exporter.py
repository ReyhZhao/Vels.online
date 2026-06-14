"""Aggregating Prometheus metrics endpoint for gunicorn multiprocess mode.

The web tier runs several gunicorn workers (see the Dockerfile CMD), each its own
process. django-prometheus records request metrics via prometheus_client, which in
multiprocess mode writes per-process samples into the shared ``PROMETHEUS_MULTIPROC_DIR``.
A single worker's ``/metrics`` would therefore only reflect that one process.

This tiny WSGI server runs as a sidecar in the backend pod, shares that directory,
and serves the *aggregated* view across all workers on a dedicated port. That port is
deliberately not wired to the public Ingress, so only the in-cluster Prometheus scraper
can reach it (ADR-0019). It depends only on prometheus_client — no Django, no DB.
"""
import os
from wsgiref.simple_server import make_server

from prometheus_client import CollectorRegistry, make_wsgi_app, multiprocess


def build_app(multiproc_dir=None):
    """Build a WSGI app that serves multiprocess-aggregated metrics.

    ``multiproc_dir`` defaults to ``PROMETHEUS_MULTIPROC_DIR``; the gunicorn workers
    must write to the same directory for the aggregation to be complete.
    """
    multiproc_dir = multiproc_dir or os.environ["PROMETHEUS_MULTIPROC_DIR"]
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry, path=multiproc_dir)
    return make_wsgi_app(registry)


def main():
    port = int(os.environ.get("METRICS_PORT", "9808"))
    httpd = make_server("0.0.0.0", port, build_app())
    httpd.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
