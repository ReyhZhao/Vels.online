from django.db.models import Q

from security.models import OrganizationMembership


def can_view_incident(user, incident):
    if user.is_staff:
        return True
    membership = OrganizationMembership.objects.filter(
        user=user, organization=incident.organization
    ).exists()
    if not membership:
        return False
    return incident.tlp != incident.TLP_RED


def filter_incidents_for_user(qs, user):
    if user.is_staff:
        return qs
    org_ids = OrganizationMembership.objects.filter(user=user).values_list(
        "organization_id", flat=True
    )
    return qs.filter(organization_id__in=org_ids).exclude(tlp="red")


def filter_events_for_user(qs, user, incident):
    """
    Staff: all events.
    Non-staff at TLP:AMBER/RED: no events (caller should 403 before reaching here).
    Non-staff at TLP:WHITE/GREEN: exclude events with is_internal=True in payload.
    """
    if user.is_staff:
        return qs
    is_member = OrganizationMembership.objects.filter(
        user=user, organization=incident.organization
    ).exists()
    if not is_member or incident.tlp in ("amber", "red"):
        return qs.none()
    # Keep events that either lack the is_internal key or have it set to False.
    # exclude(payload__is_internal=True) also drops rows where the key is absent
    # (SQL NULL comparisons are falsy), so we must be explicit.
    return qs.filter(
        Q(payload__is_internal=False) | ~Q(payload__has_key="is_internal")
    )


def filter_comments_for_user(qs, user, incident):
    """
    Staff: all comments including internal.
    Org members at TLP:WHITE/GREEN: non-internal only.
    Org members at TLP:AMBER/RED: no comments.
    Non-members: no comments.
    """
    if user.is_staff:
        return qs
    is_member = OrganizationMembership.objects.filter(
        user=user, organization=incident.organization
    ).exists()
    if not is_member:
        return qs.none()
    if incident.tlp in ("amber", "red"):
        return qs.none()
    return qs.filter(is_internal=False)
