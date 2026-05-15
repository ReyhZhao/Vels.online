import os
from datetime import timedelta

import requests
from django.utils import timezone

from .models import CveAdvisory

_UBUNTU_BASE = "https://ubuntu.com/security"
_MSRC_BASE = "https://api.msrc.microsoft.com/cvrf/v2.0"
_MSRC_ADVISORY_BASE = "https://msrc.microsoft.com/update-guide/vulnerability"
_STALENESS = timedelta(days=7)

_PLATFORM_ALIASES = {
    "darwin": "macos",
}

# Platforms with a fetch implementation in this file.
_SUPPORTED_PLATFORMS = {"ubuntu", "windows"}


def normalize_platform(raw_platform):
    """Map Wazuh os.platform values to our advisory platform keys."""
    p = (raw_platform or "").lower()
    return _PLATFORM_ALIASES.get(p, p)


class UbuntuAdvisoryError(RuntimeError):
    pass


class UbuntuAdvisoryClient:
    def fetch(self, cve_id):
        """
        Returns (advisory_url, remediation_text, raw_data).
        advisory_url and remediation_text are None when Ubuntu has no advisory for the CVE.
        Raises UbuntuAdvisoryError on non-404 HTTP failures.
        """
        url = f"{_UBUNTU_BASE}/cves/{cve_id}.json"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 404:
            return None, None, None
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise UbuntuAdvisoryError(f"Ubuntu advisory API error for {cve_id}: {exc}") from exc

        data = resp.json()
        advisory_url, remediation_text = self._parse(cve_id, data)
        return advisory_url, remediation_text, data

    def _parse(self, cve_id, data):
        notices = data.get("notices") or []
        packages = data.get("packages") or []

        released = [
            (pkg.get("name", ""), s.get("release_codename", ""), s.get("description", ""))
            for pkg in packages
            for s in (pkg.get("statuses") or [])
            if s.get("status") == "released" and s.get("description")
        ]

        if not notices and not released:
            return None, None

        advisory_url = f"{_UBUNTU_BASE}/cve/{cve_id}"

        parts = []
        if notices:
            usn_refs = ", ".join(
                f"{n['id']}" + (f": {n['title']}" if n.get("title") else "")
                for n in notices[:3]
                if n.get("id")
            )
            parts.append(f"Ubuntu has released security updates addressing this vulnerability ({usn_refs}).")

        pkg_names = list(dict.fromkeys(pkg.get("name", "") for pkg in packages if pkg.get("name")))
        if pkg_names:
            pkg_list = " ".join(pkg_names[:5])
            parts.append(
                f"Update the affected package(s) with: "
                f"sudo apt-get update && sudo apt-get upgrade {pkg_list}."
            )

        if released:
            version_lines = [
                f"{codename}: {pkg_name} {version}"
                for pkg_name, codename, version in released[:6]
            ]
            parts.append("Fixed versions — " + "; ".join(version_lines) + ".")

        return advisory_url, " ".join(parts)


class MsrcConfigError(RuntimeError):
    """Raised when MSRC_API_KEY environment variable is not set."""


class MsrcAdvisoryError(RuntimeError):
    pass


class MsrcAdvisoryClient:
    def fetch(self, cve_id):
        """
        Returns (advisory_url, remediation_text, raw_data).
        Raises MsrcConfigError if MSRC_API_KEY is not set.
        Returns (None, None, None) when the CVE is not found in MSRC.
        Raises MsrcAdvisoryError on non-404 HTTP failures.
        """
        api_key = os.environ.get("MSRC_API_KEY", "")
        if not api_key:
            raise MsrcConfigError("MSRC_API_KEY is not configured")

        url = f"{_MSRC_BASE}/cvrf/{cve_id}"
        resp = requests.get(
            url,
            headers={"api-key": api_key, "Accept": "application/json"},
            timeout=10,
        )
        if resp.status_code == 404:
            return None, None, None
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise MsrcAdvisoryError(f"MSRC advisory API error for {cve_id}: {exc}") from exc

        data = resp.json()
        advisory_url, remediation_text = self._parse(cve_id, data)
        return advisory_url, remediation_text, data

    def _parse(self, cve_id, data):
        advisory_url = f"{_MSRC_ADVISORY_BASE}/{cve_id}"

        vulnerabilities = data.get("Vulnerability") or []
        kb_articles = []
        for vuln in vulnerabilities:
            for rem in (vuln.get("Remediations") or []):
                if rem.get("Type") in ("VendorFix", "Workaround"):
                    desc = rem.get("Description", {})
                    value = desc.get("Value", "").strip() if isinstance(desc, dict) else str(desc).strip()
                    if value:
                        kb_articles.append(value)

        unique_articles = list(dict.fromkeys(kb_articles))[:5]
        if unique_articles:
            kb_list = ", ".join(unique_articles)
            remediation_text = (
                f"Microsoft has released security updates addressing this vulnerability. "
                f"Apply update(s) {kb_list} via Windows Update or the Microsoft Update Catalog. "
                f"Visit the vendor advisory for affected product versions and full details."
            )
        else:
            remediation_text = (
                "Microsoft has released security updates addressing this vulnerability. "
                "Apply available updates via Windows Update. "
                "Visit the vendor advisory for affected product versions and full details."
            )

        return advisory_url, remediation_text


def _get_client(platform):
    if platform == "ubuntu":
        return UbuntuAdvisoryClient()
    if platform == "windows":
        return MsrcAdvisoryClient()
    return None


def get_or_fetch(cve_id, platform):
    """
    Return a CveAdvisory for (cve_id, platform), fetching from the upstream API
    when no fresh cached row exists. Returns an unsaved null CveAdvisory for
    unsupported platforms, or on fetch failure when no stale row is available.
    """
    stale_row = None
    try:
        row = CveAdvisory.objects.get(cve_id=cve_id, platform=platform)
        if timezone.now() - row.fetched_at < _STALENESS:
            return row
        stale_row = row
    except CveAdvisory.DoesNotExist:
        pass

    client = _get_client(platform)
    if client is None:
        return stale_row or CveAdvisory(cve_id=cve_id, platform=platform)

    try:
        advisory_url, remediation_text, raw_data = client.fetch(cve_id)
        row, _ = CveAdvisory.objects.update_or_create(
            cve_id=cve_id,
            platform=platform,
            defaults={
                "advisory_url": advisory_url,
                "remediation_text": remediation_text,
                "fetched_at": timezone.now(),
                "raw_data": raw_data,
            },
        )
        return row
    except MsrcConfigError:
        # Key not configured — return null without storing so the next request retries.
        return stale_row or CveAdvisory(cve_id=cve_id, platform=platform)
    except Exception:
        return stale_row or CveAdvisory(cve_id=cve_id, platform=platform)
