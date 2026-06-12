"""SSRF-guarded fetch of a staff-supplied threat-report URL (ADR-0015, deep module).

A Hunt may be seeded with a link to an external malware/threat writeup. Fetching an
arbitrary, user-supplied URL server-side is a classic SSRF vector, so this module is
the hardened gate:

  - scheme allowlist (http/https only),
  - resolve the host and reject any private / loopback / link-local / reserved /
    multicast address (covers cloud metadata at 169.254.169.254),
  - cap the response size,
  - do not blindly follow redirects into internal space (one redirect hop, re-validated).

The fetched content is returned as untrusted text — the caller treats it as data to
extract IOCs from, never as instructions. The resolver is injectable so the host-block
logic is unit-testable without DNS or network.
"""
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http", "https")
MAX_BYTES = 2 * 1024 * 1024  # 2 MB
FETCH_TIMEOUT_S = 10.0


class ReportFetchError(RuntimeError):
    """Raised when a report URL is rejected or cannot be fetched safely."""


def _default_resolver(hostname: str):
    """Return the set of IP strings a hostname resolves to."""
    infos = socket.getaddrinfo(hostname, None)
    return {info[4][0] for info in infos}


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable → block
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def assert_host_allowed(hostname: str, resolver=_default_resolver) -> None:
    """Raise ReportFetchError if the host resolves to any blocked address."""
    if not hostname:
        raise ReportFetchError("missing host")
    try:
        ips = resolver(hostname)
    except Exception as exc:
        raise ReportFetchError(f"could not resolve host: {exc}") from exc
    if not ips:
        raise ReportFetchError("host did not resolve")
    for ip in ips:
        if _is_blocked_ip(ip):
            raise ReportFetchError(f"host resolves to a blocked address ({ip})")


def assert_url_allowed(url: str, resolver=_default_resolver) -> str:
    """Validate scheme + host of a URL. Returns the parsed hostname."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ReportFetchError(f"scheme '{parsed.scheme}' not allowed (http/https only)")
    if not parsed.hostname:
        raise ReportFetchError("URL has no host")
    assert_host_allowed(parsed.hostname, resolver=resolver)
    return parsed.hostname


def fetch_report(url: str, resolver=_default_resolver, session=None) -> str:
    """Fetch a report URL behind the SSRF guard and return its text (capped).

    Redirects are followed manually at most once, re-validating the target host so a
    302 cannot bounce the fetch into internal space.
    """
    sess = session or requests
    current = url
    for _hop in range(2):  # original + at most one redirect
        assert_url_allowed(current, resolver=resolver)
        resp = sess.get(
            current, timeout=FETCH_TIMEOUT_S, allow_redirects=False, stream=True,
        )
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if not location:
                raise ReportFetchError("redirect without Location")
            current = location
            continue
        if resp.status_code >= 400:
            raise ReportFetchError(f"fetch failed with status {resp.status_code}")

        body = resp.content if hasattr(resp, "content") else b""
        if isinstance(body, str):
            body = body.encode("utf-8", "ignore")
        if len(body) > MAX_BYTES:
            body = body[:MAX_BYTES]
        return body.decode("utf-8", "ignore")

    raise ReportFetchError("too many redirects")
