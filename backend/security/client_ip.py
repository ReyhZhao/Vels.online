"""Trustworthy client-IP derivation behind the reverse proxy (#696).

The app runs behind exactly one trusted reverse proxy (BunkerWeb), which terminates
TLS and forwards the connection. ``REMOTE_ADDR`` is therefore always the proxy, not
the caller — so the real client IP has to come from the forwarding headers.

SECURITY: this value backs the service-account source-IP allowlist, so it must not be
derived in a caller-spoofable way. ``X-Forwarded-For`` is an ordered list
``client, proxy1, ...`` where the *leftmost* entry is whatever the caller claimed and
is fully forgeable (a caller can pre-set the header; the proxy appends to it). With a
single trusted proxy in front, the trustworthy client IP is the entry that proxy
itself appended — the *rightmost* ``X-Forwarded-For`` value. We deliberately do NOT
trust the leftmost value (unlike the best-effort, non-security use in signups).

If ``X-Forwarded-For`` is absent or unparseable we fall back to ``REMOTE_ADDR``.
"""

import ipaddress


def get_client_ip(request):
    """Return the caller's real IP as a string, or ``None`` if undeterminable.

    Assumes a single trusted proxy: takes the rightmost ``X-Forwarded-For`` entry
    (the one our proxy appended), falling back to ``REMOTE_ADDR``.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "") or ""
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if parts:
        candidate = parts[-1]
        if _is_ip(candidate):
            return candidate
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    return remote or None


def _is_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
