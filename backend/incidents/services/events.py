from incidents.models import IncidentEvent


def record_event(incident, kind, actor=None, payload=None):
    IncidentEvent.objects.create(
        incident=incident,
        kind=kind,
        actor=actor,
        payload=payload or {},
    )
