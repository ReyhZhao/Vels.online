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
