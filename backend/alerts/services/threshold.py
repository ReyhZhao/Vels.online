from datetime import timedelta

from django.db.models import Q
from django.utils import timezone


def _get_asset_key(alert):
    """Extract the primary asset identifier from an alert's source_ref."""
    source_ref = alert.source_ref or {}
    if alert.source_kind in ('wazuh_event', 'agent_finding'):
        return source_ref.get('agent_name')
    elif alert.source_kind == 'vulnerability':
        agents = source_ref.get('affected_agents', [])
        if agents:
            first = agents[0]
            if isinstance(first, str):
                return first
            elif isinstance(first, dict):
                return first.get('agent_name')
    return None


def _asset_key_filter(source_kind, asset_key):
    """Build a Q filter to match alerts by asset key."""
    if source_kind in ('wazuh_event', 'agent_finding'):
        return Q(source_ref__agent_name=asset_key)
    elif source_kind == 'vulnerability':
        # Match first element of the affected_agents JSON array
        return Q(source_ref__affected_agents__0=asset_key)
    return Q(pk__in=[])  # No match for unknown source_kind


def check_asset_threshold(alert):
    """
    Return True if the count of 'new' alerts for the same asset within the
    auto-promote window meets or exceeds the org threshold.
    """
    from alerts.models import Alert

    org = alert.organization
    asset_key = _get_asset_key(alert)
    if not asset_key:
        return False

    window_start = timezone.now() - timedelta(minutes=org.alert_auto_promote_window_minutes)

    count = Alert.objects.filter(
        organization=org,
        source_kind=alert.source_kind,
        state='new',
        created_at__gte=window_start,
    ).filter(_asset_key_filter(alert.source_kind, asset_key)).count()

    return count >= org.alert_auto_promote_threshold
