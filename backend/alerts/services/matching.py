from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from incidents.models import Incident


def find_matching_incident(alert):
    """
    Find the most recent open incident matching the alert's source_kind and source_ref.

    Matching criteria:
      - Same organization
      - Same source_kind
      - Created within org.alert_match_lookback_days
      - Not closed
      - source_ref rule_id OR rule_description matches
    """
    org = alert.organization
    lookback = timezone.now() - timedelta(days=org.alert_match_lookback_days)

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
