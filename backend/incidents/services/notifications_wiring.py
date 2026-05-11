"""
Thin helpers called from incidents.views to fire notifications.
Kept separate so views.py stays readable and circular-import risk is contained.
"""
from django.contrib.auth.models import User

HIGH_SEVERITY = {"critical", "high"}
TLP_SHARABLE = {"white", "green", "amber"}  # not red


def notify_comment(incident, comment, actor):
    from incidents.models import IncidentDelegation
    from notifications.services.notifications import notify

    recipients = []
    if incident.assignee_id:
        try:
            recipients.append(User.objects.get(pk=incident.assignee_id))
        except User.DoesNotExist:
            pass

    delegate_ids = IncidentDelegation.objects.filter(
        incident=incident, returned_at__isnull=True
    ).values_list("user_id", flat=True)
    delegate_users = list(User.objects.filter(id__in=delegate_ids))

    all_recipients = [
        u for u in {u.id: u for u in recipients + delegate_users}.values()
        if u.id != actor.id
    ]

    if all_recipients:
        notify(
            "comment",
            all_recipients,
            incident=incident,
            payload={
                "title": f"New comment on {incident.display_id}",
                "body": comment.body[:200],
                "link": f"/incidents/{incident.id}",
            },
        )


def notify_incident_alert_if_needed(incident):
    if incident.severity not in HIGH_SEVERITY or incident.tlp not in TLP_SHARABLE:
        return
    _fire_incident_alert(incident, f"New {incident.severity} severity incident: {incident.display_id}")


def notify_severity_bump_if_needed(incident, old_severity):
    if (
        old_severity not in HIGH_SEVERITY
        and incident.severity in HIGH_SEVERITY
        and incident.tlp in TLP_SHARABLE
    ):
        _fire_incident_alert(
            incident,
            f"{incident.display_id} severity raised to {incident.severity}",
        )


def _fire_incident_alert(incident, title):
    from security.models import OrganizationMembership
    from notifications.services.notifications import notify

    member_ids = OrganizationMembership.objects.filter(
        organization=incident.organization
    ).values_list("user_id", flat=True)
    members = list(User.objects.filter(id__in=member_ids, is_active=True))

    if members:
        notify(
            "incident_alert",
            members,
            incident=incident,
            payload={
                "title": title,
                "body": incident.title,
                "link": f"/incidents/{incident.id}",
            },
        )
