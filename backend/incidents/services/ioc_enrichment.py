"""IOC enrichment service — AbuseIPDB (IP) and VirusTotal (domain/URL)."""
import logging
import time
from datetime import timezone as dt_timezone, datetime

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24 hours
_MAX_RETRIES = 3


def _cache_key(kind: str, value: str) -> str:
    return f"ioc_enrichment:{kind}:{value}"


def _now_iso() -> str:
    return datetime.now(tz=dt_timezone.utc).isoformat(timespec="seconds")


def _enrich_ip(value: str) -> dict:
    api_key = getattr(settings, "ABUSEIPDB_API_KEY", None)
    if not api_key:
        logger.warning("ioc_enrichment: ABUSEIPDB_API_KEY not configured — skipping IP enrichment")
        return {}

    cached = cache.get(_cache_key("ip", value))
    if cached is not None:
        return cached

    headers = {"Key": api_key, "Accept": "application/json"}
    params = {"ipAddress": value, "maxAgeInDays": 90}

    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(
                "https://api.abuseipdb.com/api/v2/check",
                headers=headers,
                params=params,
                timeout=15,
            )
        except requests.RequestException as exc:
            last_exc = exc
            backoff = 30 * (2 ** attempt)
            logger.warning("ioc_enrichment: AbuseIPDB request error (attempt %d): %s — retrying in %ds", attempt + 1, exc, backoff)
            time.sleep(backoff)
            continue

        if resp.status_code == 429:
            result = {"abuseipdb": {"status": "failed", "checked_at": _now_iso(), "error": "rate_limited"}}
            cache.set(_cache_key("ip", value), result, _CACHE_TTL)
            return result

        if resp.status_code >= 500:
            last_exc = Exception(f"HTTP {resp.status_code}")
            backoff = 30 * (2 ** attempt)
            logger.warning("ioc_enrichment: AbuseIPDB 5xx (attempt %d): %s — retrying in %ds", attempt + 1, resp.status_code, backoff)
            time.sleep(backoff)
            continue

        resp.raise_for_status()
        data = resp.json().get("data", {})
        result = {
            "abuseipdb": {
                "status": "done",
                "checked_at": _now_iso(),
                "abuse_confidence_score": data.get("abuseConfidenceScore"),
                "total_reports": data.get("totalReports"),
                "country_code": data.get("countryCode"),
                "usage_type": data.get("usageType"),
            }
        }
        cache.set(_cache_key("ip", value), result, _CACHE_TTL)
        return result

    result = {"abuseipdb": {"status": "failed", "checked_at": _now_iso(), "error": f"max retries exceeded: {last_exc}"}}
    cache.set(_cache_key("ip", value), result, _CACHE_TTL)
    return result


def _enrich_domain_or_url(kind: str, value: str) -> dict:
    api_key = getattr(settings, "VIRUSTOTAL_API_KEY", None)
    if not api_key:
        logger.warning("ioc_enrichment: VIRUSTOTAL_API_KEY not configured — skipping %s enrichment", kind)
        return {}

    cached = cache.get(_cache_key(kind, value))
    if cached is not None:
        return cached

    headers = {"x-apikey": api_key}

    if kind == "domain":
        url = f"https://www.virustotal.com/api/v3/domains/{value}"
    else:
        import base64
        encoded = base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")
        url = f"https://www.virustotal.com/api/v3/urls/{encoded}"

    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
        except requests.RequestException as exc:
            last_exc = exc
            backoff = 30 * (2 ** attempt)
            logger.warning("ioc_enrichment: VirusTotal request error (attempt %d): %s — retrying in %ds", attempt + 1, exc, backoff)
            time.sleep(backoff)
            continue

        if resp.status_code == 429:
            result = {"virustotal": {"status": "failed", "checked_at": _now_iso(), "error": "rate_limited"}}
            cache.set(_cache_key(kind, value), result, _CACHE_TTL)
            return result

        if resp.status_code >= 500:
            last_exc = Exception(f"HTTP {resp.status_code}")
            backoff = 30 * (2 ** attempt)
            logger.warning("ioc_enrichment: VirusTotal 5xx (attempt %d): %s — retrying in %ds", attempt + 1, resp.status_code, backoff)
            time.sleep(backoff)
            continue

        resp.raise_for_status()
        stats = resp.json().get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
        result = {
            "virustotal": {
                "status": "done",
                "checked_at": _now_iso(),
                "malicious": stats.get("malicious", 0),
                "suspicious": stats.get("suspicious", 0),
                "total": sum(stats.values()) if stats else 0,
            }
        }
        cache.set(_cache_key(kind, value), result, _CACHE_TTL)
        return result

    result = {"virustotal": {"status": "failed", "checked_at": _now_iso(), "error": f"max retries exceeded: {last_exc}"}}
    cache.set(_cache_key(kind, value), result, _CACHE_TTL)
    return result


def enrich_ioc(ioc) -> dict:
    """Return enrichment data dict for the given IOC. Never raises."""
    try:
        if ioc.kind == "ip":
            return _enrich_ip(ioc.value)
        if ioc.kind in ("domain", "url"):
            return _enrich_domain_or_url(ioc.kind, ioc.value)
        return {}
    except Exception as exc:
        logger.error("ioc_enrichment: unexpected error enriching %s %r: %s", ioc.kind, ioc.value, exc)
        return {}
