import logging
from datetime import date

from celery import shared_task
from django.contrib.auth.models import User
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task
def snapshot_vulnerabilities():
    from notifications.services.notifications import notify
    from security.models import Organization, VulnerabilitySnapshot
    from security.opensearch import OpenSearchClient, OpenSearchError
    from security.wazuh import WazuhClient, WazuhAPIError, WazuhAuthError

    today = date.today()
    os_client = OpenSearchClient()

    for org in Organization.objects.all():
        try:
            raw_agents = WazuhClient().get_agents(org.wazuh_group)
            agent_ids = [a["id"] for a in raw_agents if a.get("status") == "active"]

            counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            current_cve_ids = []

            if agent_ids:
                result = os_client.get_fleet_vulnerabilities(agent_ids, limit=10000)
                all_vulns = result["vulnerabilities"]
                current_cve_ids = [v["cve"] for v in all_vulns]
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

            with transaction.atomic():
                VulnerabilitySnapshot.objects.update_or_create(
                    organization=org,
                    date=today,
                    defaults={
                        **counts,
                        "new_count": len(current_ids - prev_ids),
                        "resolved_count": len(prev_ids - current_ids),
                        "cve_ids": current_cve_ids,
                    },
                )

        except (WazuhAuthError, WazuhAPIError, OpenSearchError) as exc:
            logger.exception("snapshot_vulnerabilities failed for org %s: %s", org.slug, exc)
            staff = list(User.objects.filter(is_staff=True, is_active=True))
            if staff:
                notify(
                    "system_alert",
                    staff,
                    payload={
                        "title": "Vulnerability snapshot failed",
                        "body": f"Failed to snapshot vulnerabilities for {org.name}: {exc}",
                        "link": "/security/vulnerabilities",
                    },
                )


@shared_task
def generate_work_packages():
    from security.models import Organization
    from security.work_package_service import cleanup_old_packages, generate_work_package

    for org in Organization.objects.all():
        generate_work_package(org)

    cleanup_old_packages()
