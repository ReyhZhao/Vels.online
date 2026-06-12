from datetime import timedelta

from incidents.models import IncidentEvent

# A run of alert_linked events by the same actor whose neighbours fall within this
# window is collapsed into one "N alerts were linked" timeline entry (issue #499).
ALERT_LINKED_COLLAPSE_WINDOW = timedelta(minutes=5)


def record_event(incident, kind, actor=None, payload=None):
    IncidentEvent.objects.create(
        incident=incident,
        kind=kind,
        actor=actor,
        payload=payload or {},
    )


def _collapsed_alert_linked(run):
    """Build a serializer-shaped synthetic entry for a collapsed alert_linked run."""
    first = run[0]
    display_ids = [
        e.payload.get("alert_display_id")
        for e in run
        if isinstance(e.payload, dict) and e.payload.get("alert_display_id")
    ]
    return {
        "id": f"alert-linked-bulk-{first.id}",
        "kind": "alert_linked",
        "actor": first.actor_id,
        "actor_username": first.actor.username if first.actor else None,
        "payload": {
            "collapsed": True,
            "count": len(run),
            "alert_display_ids": display_ids,
        },
        "created_at": first.created_at.isoformat(),
    }


def collapse_alert_linked_events(events, window=ALERT_LINKED_COLLAPSE_WINDOW):
    """Fold bursts of alert_linked events into single entries for timeline display.

    Takes IncidentEvent instances ordered by created_at and returns serializer-shaped
    dicts. A maximal run of consecutive alert_linked events by the same actor, each
    within `window` of its predecessor, collapses to one synthetic entry carrying a
    count and the contributing alert display ids. Lone alert_linked events and all
    other kinds pass through serialized as-is. The underlying rows are untouched —
    this is presentation only. Folding happens before pagination so a burst that
    would straddle a page boundary still collapses.
    """
    from incidents.serializers import IncidentEventSerializer

    events = list(events)
    out = []
    i = 0
    n = len(events)
    while i < n:
        ev = events[i]
        if ev.kind != "alert_linked":
            out.append(IncidentEventSerializer(ev).data)
            i += 1
            continue

        run = [ev]
        j = i + 1
        while j < n:
            nxt = events[j]
            if (
                nxt.kind == "alert_linked"
                and nxt.actor_id == ev.actor_id
                and (nxt.created_at - run[-1].created_at) <= window
            ):
                run.append(nxt)
                j += 1
            else:
                break

        if len(run) >= 2:
            out.append(_collapsed_alert_linked(run))
        else:
            out.append(IncidentEventSerializer(ev).data)
        i = j

    return out
