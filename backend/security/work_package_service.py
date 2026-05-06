from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from security.models import WorkPackage, WorkPackageItem
from security.opensearch import OpenSearchClient, OpenSearchError
from security.scoring import score_vulnerabilities
from security.wazuh import WazuhClient, WazuhAPIError, WazuhAuthError

_MAX_ITEMS = 10
_ARCHIVE_RETENTION_WEEKS = 12


def generate_work_package(org, generated_by=None):
    """
    Generate a new active WorkPackage for org.

    Archives the current active package, then creates a new one with the top
    scored CVEs snapshotted as WorkPackageItems. Returns the new WorkPackage,
    or None if no agent/CVE data is available or an external call fails.
    """
    try:
        raw_agents = WazuhClient().get_agents(org.wazuh_group)
    except (WazuhAuthError, WazuhAPIError):
        return None

    agent_ids = [a["id"] for a in raw_agents if a.get("status") == "active"]
    if not agent_ids:
        return None

    os_client = OpenSearchClient()
    try:
        result = os_client.get_fleet_vulnerabilities(agent_ids, limit=10000)
    except OpenSearchError:
        return None

    all_vulns = result["vulnerabilities"]
    if not all_vulns:
        return None

    scored = score_vulnerabilities([
        {"cve_id": v["cve"], "severity": v["severity"], "agent_count": v["affected_agents"]}
        for v in all_vulns
    ])
    top = scored[:_MAX_ITEMS]

    vuln_by_cve = {v["cve"]: v for v in all_vulns}

    with transaction.atomic():
        WorkPackage.objects.filter(org=org, status=WorkPackage.STATUS_ACTIVE).update(
            status=WorkPackage.STATUS_ARCHIVED
        )
        package = WorkPackage.objects.create(org=org, generated_by=generated_by)

        items = []
        for entry in top:
            cve_id = entry["cve_id"]
            vuln = vuln_by_cve.get(cve_id, {})

            try:
                hits = os_client.get_cve_affected_agents(agent_ids, cve_id)
            except OpenSearchError:
                hits = []

            affected_agents = [
                {
                    "agent_id": h.get("agent", {}).get("id", ""),
                    "hostname": h.get("agent", {}).get("name", ""),
                    "package_name": h.get("package", {}).get("name", ""),
                    "current_version": h.get("package", {}).get("version", ""),
                    "fixed_version": None,
                    "patch_job_id": None,
                }
                for h in hits
            ]

            description = ""
            references = []
            if hits:
                vuln_detail = hits[0].get("vulnerability", {})
                description = vuln_detail.get("description", "") or ""
                raw_refs = vuln_detail.get("references", [])
                references = raw_refs if isinstance(raw_refs, list) else []

            items.append(WorkPackageItem(
                work_package=package,
                cve_id=cve_id,
                severity=entry["severity"],
                cvss_score=vuln.get("cvss_score") or 0.0,
                description=description,
                references=references,
                affected_agent_count=entry["affected_agent_count"],
                impact_score=entry["impact_score"],
                affected_agents=affected_agents,
            ))

        WorkPackageItem.objects.bulk_create(items)

    return package


_ADD_MORE_BATCH = 5


def add_more_items(package):
    """
    Append up to 5 next-ranked CVEs not already in package.

    Returns (new_items: list[WorkPackageItem], exhausted: bool).
    exhausted is True when no further CVEs exist beyond the current package.
    Returns ([], False) on external service failure.
    """
    org = package.org
    existing_cve_ids = set(package.items.values_list("cve_id", flat=True))

    try:
        raw_agents = WazuhClient().get_agents(org.wazuh_group)
    except (WazuhAuthError, WazuhAPIError):
        return [], False

    agent_ids = [a["id"] for a in raw_agents if a.get("status") == "active"]
    if not agent_ids:
        return [], True

    os_client = OpenSearchClient()
    try:
        result = os_client.get_fleet_vulnerabilities(agent_ids, limit=10000)
    except OpenSearchError:
        return [], False

    all_vulns = result["vulnerabilities"]
    if not all_vulns:
        return [], True

    scored = score_vulnerabilities([
        {"cve_id": v["cve"], "severity": v["severity"], "agent_count": v["affected_agents"]}
        for v in all_vulns
    ])

    candidates = [e for e in scored if e["cve_id"] not in existing_cve_ids]
    exhausted = len(candidates) <= _ADD_MORE_BATCH
    batch = candidates[:_ADD_MORE_BATCH]

    if not batch:
        return [], True

    vuln_by_cve = {v["cve"]: v for v in all_vulns}
    new_items = []

    with transaction.atomic():
        for entry in batch:
            cve_id = entry["cve_id"]
            vuln = vuln_by_cve.get(cve_id, {})

            try:
                hits = os_client.get_cve_affected_agents(agent_ids, cve_id)
            except OpenSearchError:
                hits = []

            affected_agents = [
                {
                    "agent_id": h.get("agent", {}).get("id", ""),
                    "hostname": h.get("agent", {}).get("name", ""),
                    "package_name": h.get("package", {}).get("name", ""),
                    "current_version": h.get("package", {}).get("version", ""),
                    "fixed_version": None,
                    "patch_job_id": None,
                }
                for h in hits
            ]

            description = ""
            references = []
            if hits:
                vuln_detail = hits[0].get("vulnerability", {})
                description = vuln_detail.get("description", "") or ""
                raw_refs = vuln_detail.get("references", [])
                references = raw_refs if isinstance(raw_refs, list) else []

            item = WorkPackageItem.objects.create(
                work_package=package,
                cve_id=cve_id,
                severity=entry["severity"],
                cvss_score=vuln.get("cvss_score") or 0.0,
                description=description,
                references=references,
                affected_agent_count=entry["affected_agent_count"],
                impact_score=entry["impact_score"],
                affected_agents=affected_agents,
            )
            new_items.append(item)

    return new_items, exhausted


def cleanup_old_packages():
    """Delete archived WorkPackages older than 12 weeks."""
    cutoff = timezone.now() - timedelta(weeks=_ARCHIVE_RETENTION_WEEKS)
    deleted, _ = WorkPackage.objects.filter(
        status=WorkPackage.STATUS_ARCHIVED,
        created_at__lt=cutoff,
    ).delete()
    return deleted
