import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def route_triaged_incident(incident, triage_result) -> None:
    try:
        _do_route(incident, triage_result)
    except Exception:
        logger.warning("Routing failure for incident %s", incident.pk, exc_info=True)


def _do_route(incident, triage_result):
    mode = getattr(settings, "ONCALL_ROUTING", "always")
    if mode not in ("always", "llm_guided"):
        logger.warning("Unknown ONCALL_ROUTING=%r, falling back to always", mode)
        mode = "always"

    if mode == "llm_guided":
        trigger_actions = {"escalate", "assign_to_analyst"}
        primary = getattr(triage_result, "primary_action", None)
        secondary = getattr(triage_result, "secondary_action", None)
        if primary not in trigger_actions and secondary not in trigger_actions:
            return

    from django.utils import timezone as tz
    from oncall.services.resolver import get_oncall_analyst
    analyst = get_oncall_analyst(at=tz.now())

    if analyst is None:
        from notifications.services.notifications import notify
        from django.contrib.auth.models import User
        staff_users = list(User.objects.filter(is_staff=True, is_active=True))
        notify("system_alert", staff_users, incident=incident, payload={
            "title": "On-call gap",
            "body": f"No on-call analyst found to assign incident {incident.display_id}.",
        })
        return

    incident.assignee = analyst
    incident.save(update_fields=["assignee"])

    from incidents.services.events import record_event
    record_event(incident, actor=None, kind="assigned", payload={"assignee_id": analyst.id, "via": "oncall_routing"})

    from notifications.services.notifications import notify
    notify("assignment", [analyst], incident=incident, payload={
        "title": f"Incident {incident.display_id} assigned to you",
        "body": "You are the on-call analyst and have been automatically assigned this incident.",
        "link": f"/incidents/{incident.display_id}",
    })
