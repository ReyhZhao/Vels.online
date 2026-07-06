"""Match an inbound partner email onto an existing Incident by External Reference
(ADR-0032), mirroring alerts.services.matching. The join key is
`(connection, external_reference)` over the Connection's own open partner incidents."""


def find_partner_incident(connection, external_reference):
    """Return the most recent open Partner Incident for (connection, external_reference),
    or None. An empty reference never matches — a report with no ref always opens a new
    incident (slice 4)."""
    from incidents.models import Incident

    ref = (external_reference or "").strip()
    if not ref:
        return None
    return (
        Incident.objects.filter(
            source_kind=Incident.SOURCE_PARTNER,
            source_ref__connection_id=connection.id,
            source_ref__external_reference=ref,
        )
        .exclude(state=Incident.STATE_CLOSED)
        .order_by("-created_at")
        .first()
    )
