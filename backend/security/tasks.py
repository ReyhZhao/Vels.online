from datetime import date

from celery import shared_task
from django.db import transaction


@shared_task
def snapshot_vulnerabilities():
    from security.models import Organization, VulnerabilitySnapshot
    from security.opensearch import OpenSearchClient, OpenSearchError
    from security.wazuh import WazuhClient, WazuhAPIError, WazuhAuthError

    today = date.today()
    os_client = OpenSearchClient()

    for org in Organization.objects.all():
        try:
            raw_agents = WazuhClient().get_agents(org.wazuh_group)
            agent_ids = [a["id"] for a in raw_agents if a.get("status") == "active"]
            if not agent_ids:
                _upsert_snapshot(org, today, {}, [], [])
                continue

            result = os_client.get_fleet_vulnerabilities(agent_ids, limit=10000)
            all_vulns = result["vulnerabilities"]
            current_cve_ids = [v["cve"] for v in all_vulns]

            counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for v in all_vulns:
                sev = v["severity"]
                if sev in counts:
                    counts[sev] += 1

            prev = (
                VulnerabilitySnapshot.objects
                .filter(organization=org, date__lt=today)
                .order_by("-date")
                .first()
            )
            prev_ids = set(prev.cve_ids) if prev else set()
            current_ids = set(current_cve_ids)
            new_count = len(current_ids - prev_ids)
            resolved_count = len(prev_ids - current_ids)

            with transaction.atomic():
                VulnerabilitySnapshot.objects.update_or_create(
                    organization=org,
                    date=today,
                    defaults={
                        **counts,
                        "new_count": new_count,
                        "resolved_count": resolved_count,
                        "cve_ids": current_cve_ids,
                    },
                )
        except (WazuhAuthError, WazuhAPIError, OpenSearchError):
            continue
