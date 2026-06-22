"""Celery-beat producer task for the Live Attack Map (PRD #594, ADR-0027).

Fires every ~10s (seeded as a django_celery_beat PeriodicTask). The task is always
scheduled but short-circuits instantly when nobody is watching, so OpenSearch sees
zero attack-map queries while the map is idle.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def produce_attack_snapshot():
    from security.opensearch import OpenSearchClient
    from security.wazuh import WazuhClient

    from .producer import run_snapshot_tick

    try:
        result = run_snapshot_tick(OpenSearchClient(), WazuhClient())
    except Exception:  # a transient OpenSearch/Wazuh blip must not crash beat
        logger.exception("produce_attack_snapshot tick failed")
        return {"error": True}
    return result
