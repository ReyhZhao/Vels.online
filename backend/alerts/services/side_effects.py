from alerts.models import SEVERITY_ORDER
from incidents.services.events import record_event
from incidents.services.promote import link_source_assets
from incidents.services.notifications_wiring import notify_severity_bump_if_needed


def apply_link_side_effects(alert, incident):
    """Fire all side effects when an alert is linked to an incident."""
    # 1. Record a timeline event on the incident
    agent_name = (alert.source_ref or {}).get('agent_name', '')
    record_event(incident, 'alert_linked', payload={
        'alert_display_id': alert.display_id,
        'source_kind': alert.source_kind,
        'agent_name': agent_name,
    })

    # 2. Bump incident severity if alert severity is strictly higher
    if SEVERITY_ORDER.get(alert.severity, 0) > SEVERITY_ORDER.get(incident.severity, 0):
        old_severity = incident.severity
        incident.severity = alert.severity
        incident.save(update_fields=['severity'])
        notify_severity_bump_if_needed(incident, old_severity)

    # 3. Link source assets referenced by the alert's source_ref
    link_source_assets(incident, incident.organization)

    # 4. Notify the incident assignee if one is set
    if incident.assignee_id:
        _notify_assignee(incident, alert)


def _notify_assignee(incident, alert):
    try:
        from django.contrib.auth.models import User
        from notifications.services.notifications import notify

        assignee = User.objects.get(pk=incident.assignee_id)
        notify(
            'alert_linked',
            [assignee],
            incident=incident,
            payload={
                'title': f'New alert linked to {incident.display_id}',
                'body': alert.title,
                'link': f'/incidents/{incident.display_id}',
            },
        )
    except Exception:
        pass
