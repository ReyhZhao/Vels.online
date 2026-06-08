from django.core.exceptions import ValidationError
from django.db import transaction

from incidents.services.events import record_event

# Org change is a triage-time correction. Almost every incident sits in `triaged`
# after auto-triage before a human sees it, so `triaged` must be permitted.
TRIAGE_STATES = {"new", "triaged"}


def change_incident_org(incident, new_org, actor):
    """Move an incident to a different organisation, preserving tenant isolation.

    Relinks the incident's linked Alerts to the new org (the incident↔alerts same-org
    invariant must hold), detaches its asset links (assets are per-org enrollments and
    are never migrated across tenants — the Asset rows themselves are untouched), and
    records one audit event. Subject (global) and assignee (a staff user) are left
    unchanged. Atomic: a failure leaves the incident, alerts, and asset links unchanged.
    """
    if incident.state not in TRIAGE_STATES:
        raise ValidationError(
            "Org can only be changed while the incident is in the new or triaged state."
        )
    if new_org.id == incident.organization_id:
        raise ValidationError("The incident is already in that organisation.")

    old_org = incident.organization

    with transaction.atomic():
        alerts_relinked = incident.alerts.update(organization=new_org)
        assets_unlinked, _ = incident.incident_assets.all().delete()

        incident.organization = new_org
        incident.save(update_fields=["organization"])

        record_event(
            incident,
            "incident_org_changed",
            actor=actor,
            payload={
                "from": old_org.slug,
                "to": new_org.slug,
                "alerts_relinked": alerts_relinked,
                "assets_unlinked": assets_unlinked,
            },
        )

    return incident
