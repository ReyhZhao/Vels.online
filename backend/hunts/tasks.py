"""Celery entry point for a Hunt turn (ADR-0016).

Each turn runs as a background job so execution lifetime is decoupled from the SSE
connection: the worker keeps running (and writing events) whether or not a client is
listening, and a reconnecting client tails the persisted event log.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_hunt_turn_task(hunt_id, messages):
    from incidents.llm.factory import get_assistant_provider
    from .models import Hunt
    from .orchestration import run_hunt_turn

    try:
        hunt = Hunt.objects.get(pk=hunt_id)
    except Hunt.DoesNotExist:
        logger.warning("run_hunt_turn_task: hunt %s gone", hunt_id)
        return

    provider = get_assistant_provider()
    return run_hunt_turn(hunt, messages, provider=provider)
