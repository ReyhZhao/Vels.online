from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from incidents.models import Incident


def find_matching_incident(alert):
    """
    Find the most recent open incident matching the alert's source_kind and source_ref.
    """
    org = alert.organization
    lookback = timezone.now() - timedelta(days=org.alert_match_lookback_days)

    if alert.source_kind == "inbound_email":
        return _find_matching_inbound_email_incident(alert, org, lookback)

    source_ref = alert.source_ref or {}
    rule_id = source_ref.get('rule_id')
    rule_description = source_ref.get('rule_description')

    if not rule_id and not rule_description:
        return None

    qs = Incident.objects.filter(
        organization=org,
        source_kind=alert.source_kind,
        created_at__gte=lookback,
    ).exclude(state='closed')

    q = Q()
    if rule_id:
        q |= Q(source_ref__rule_id=rule_id)
    if rule_description:
        q |= Q(source_ref__rule_description=rule_description)

    return qs.filter(q).order_by('-created_at').first()


def _find_matching_inbound_email_incident(alert, org, lookback):
    source_ref = alert.source_ref or {}
    sender_address = source_ref.get("sender_address")
    subject_normalised = source_ref.get("subject_normalised")

    if not sender_address or not subject_normalised:
        return None

    return (
        Incident.objects.filter(
            organization=org,
            source_kind="inbound_email",
            created_at__gte=lookback,
            source_ref__sender_address=sender_address,
            source_ref__subject_normalised=subject_normalised,
        )
        .exclude(state="closed")
        .order_by("-created_at")
        .first()
    )
