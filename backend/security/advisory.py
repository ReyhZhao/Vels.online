from datetime import timedelta

import requests
from django.utils import timezone

from .models import CveAdvisory

_UBUNTU_BASE = "https://ubuntu.com/security"
_STALENESS = timedelta(days=7)

_PLATFORM_ALIASES = {
    "darwin": "macos",
}

# Platforms with a fetch implementation in this file.
_SUPPORTED_PLATFORMS = {"ubuntu"}


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

    if platform not in _SUPPORTED_PLATFORMS:
        return stale_row or CveAdvisory(cve_id=cve_id, platform=platform)

    try:
        advisory_url, remediation_text, raw_data = UbuntuAdvisoryClient().fetch(cve_id)
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
    except Exception:
        return stale_row or CveAdvisory(cve_id=cve_id, platform=platform)
