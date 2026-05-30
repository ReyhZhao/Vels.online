from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from incidents.services.identifiers import next_display_id
from incidents.services.promote import build_promote_payload, link_source_assets
from incidents.services.events import record_event
from incidents.serializers import IncidentCreateSerializer

from .matching import find_matching_incident
from .side_effects import apply_link_side_effects
from .threshold import check_asset_threshold, _get_asset_key, _asset_key_filter


def derive_incident_fields(alert):
    """
    Return a dict of incident fields derived from an alert.
    Explicit alert fields take precedence over auto-derived values from build_promote_payload.
    """
    payload = build_promote_payload(alert.source_kind, alert.source_ref or {})
    if alert.title:
        payload["title"] = alert.title
    if alert.description is not None:
        payload["description"] = alert.description
    if alert.severity is not None:
        payload["severity"] = alert.severity
    if alert.pap is not None:
        payload["pap"] = alert.pap
    if alert.tlp is not None:
        payload["tlp"] = alert.tlp
    return payload


def _create_incident_from_alert(alert, org, overrides=None):
    """Create a new Incident from an alert, preferring explicit alert fields over auto-derived values.

    overrides: optional dict of analyst-supplied fields (e.g. from bulk-promote dialog)
    that take highest precedence over both auto-derived and alert-level explicit values.
    """
    payload = derive_incident_fields(alert)
    if overrides:
        payload.update({k: v for k, v in overrides.items() if v is not None})

    ser = IncidentCreateSerializer(data=payload)
    ser.is_valid(raise_exception=True)

    with transaction.atomic():
        display_id = next_display_id()
        incident = ser.save(
            organization=org,
            display_id=display_id,
            created_by=None,
        )
        link_source_assets(incident, org)
        record_event(incident, 'incident_created', payload={
            'source': 'alert_auto_promote',
            'alert_display_id': alert.display_id,
        })

        # Best-effort: extract IOCs and kick off triage
        try:
            from incidents.services.ioc_extraction import extract_and_save_iocs
            from incidents.tasks import acquire_triage_lock, enrich_iocs_then_triage

            extract_and_save_iocs(incident)
            if acquire_triage_lock(incident.id):
                incident_id = incident.id
                transaction.on_commit(lambda: enrich_iocs_then_triage.delay(incident_id))
        except Exception:
            pass

    return incident


def route_alert(alert):
    """
    Main routing entry point. Called after an alert is created (state='new').
    May mutate alert.state and alert.incident if routing produces a match.
    """
    org = alert.organization

    # Step 1: Auto-link to an existing open incident with the same rule
    match = find_matching_incident(alert)
    if match:
        alert.state = 'imported'
        alert.incident = match
        alert.save(update_fields=['state', 'incident', 'updated_at'])
        apply_link_side_effects(alert, match)
        return

    # Step 2: Auto-promote high/critical alerts to a brand-new incident
    if alert.severity in ('high', 'critical'):
        incident = _create_incident_from_alert(alert, org)
        alert.state = 'imported'
        alert.incident = incident
        alert.save(update_fields=['state', 'incident', 'updated_at'])
        apply_link_side_effects(alert, incident)
        return

    # Step 3: Asset threshold – if this asset has generated enough alerts in the
    # promotion window, promote all of them to a single new incident.
    if check_asset_threshold(alert):
        asset_key = _get_asset_key(alert)
        if not asset_key:
            return

        window_start = timezone.now() - timedelta(minutes=org.alert_auto_promote_window_minutes)

        with transaction.atomic():
            qualifying = list(
                _alert_model().objects.select_for_update().filter(
                    organization=org,
                    source_kind=alert.source_kind,
                    state='new',
                    created_at__gte=window_start,
                ).filter(_asset_key_filter(alert.source_kind, asset_key))
            )

            if not qualifying:
                return

            incident = _create_incident_from_alert(alert, org)

            for a in qualifying:
                a.state = 'imported'
                a.incident = incident
                a.save(update_fields=['state', 'incident', 'updated_at'])
                apply_link_side_effects(a, incident)


def _alert_model():
    from alerts.models import Alert
    return Alert
