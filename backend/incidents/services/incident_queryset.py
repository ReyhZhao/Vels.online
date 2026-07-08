"""Shared incident-queryset scoping.

The tenant scoping (`filter_incidents_for_user`) and tab logic (all / my_queue /
unassigned, including the implicit "exclude closed when no explicit state") are
needed identically by the incident list view and the incident trend endpoint.
Keeping them in one place stops the two from drifting apart.
"""
from django.db.models import Q

from incidents.models import Incident, IncidentDelegation
from incidents.services.visibility import filter_incidents_for_user


def build_incident_queryset(user, query_params, base_qs=None):
    """Return a tenant-scoped, tab-filtered ``Incident`` queryset.

    Applies, in order:
      * tenant visibility (`filter_incidents_for_user`),
      * the ``tab`` constraint (``all`` / ``my_queue`` / ``unassigned``),
      * the implicit "exclude closed when no explicit ``state``" rule.

    The implicit exclusion can be turned off with ``include_closed`` (truthy),
    which lets a caller populate over every state without having to enumerate
    them via ``state``. The dashboard trend chart uses this so it reflects all
    incidents regardless of state.

    It deliberately does **not** apply the ``IncidentFilterSet`` field filters
    (severity / state / q / org / …) — those are layered on afterwards by the
    list view's filter backend or the trend endpoint, so both callers share the
    scoping but keep control of the rest of the query.

    ``query_params`` is a ``QueryDict`` (``request.query_params``).
    """
    qs = base_qs if base_qs is not None else Incident.objects.all()
    qs = filter_incidents_for_user(qs, user)

    tab = query_params.get("tab", "all")
    explicit_states = [
        c.strip()
        for v in query_params.getlist("state")
        for c in v.split(",") if c.strip()
    ]
    include_closed = query_params.get("include_closed") in ("1", "true", "True")

    if tab == "my_queue":
        delegated = IncidentDelegation.objects.filter(
            user=user, returned_at__isnull=True
        ).values_list("incident_id", flat=True)
        qs = qs.filter(Q(assignee=user) | Q(id__in=delegated))
    elif tab == "unassigned":
        qs = qs.filter(assignee__isnull=True)

    if not explicit_states and not include_closed:
        qs = qs.exclude(state="closed")

    return qs
