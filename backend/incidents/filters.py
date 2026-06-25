import json
from datetime import timedelta

import django_filters
from django.db.models import Q
from django.utils import timezone

from .models import Asset, Incident, Task, TaskTemplate


def _parse_duration(value):
    """Parse '1h', '24h', '7d', '30d' → timedelta. Returns None on bad input."""
    v = value.strip().lower()
    try:
        if v.endswith("h"):
            return timedelta(hours=float(v[:-1]))
        if v.endswith("d"):
            return timedelta(days=float(v[:-1]))
    except (ValueError, TypeError):
        pass
    return None


class IncidentFilterSet(django_filters.FilterSet):
    # Multi-value filters: accept 'state=new,triaged' or '?state=new&state=triaged'
    state = django_filters.CharFilter(method="filter_state")
    severity = django_filters.CharFilter(method="filter_severity")
    tlp = django_filters.CharFilter(method="filter_tlp")

    # Simple field lookups
    org = django_filters.CharFilter(field_name="organization__slug", lookup_expr="exact")
    subject = django_filters.CharFilter(method="filter_subject")
    source_kind = django_filters.CharFilter(field_name="source_kind", lookup_expr="exact")
    title = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    # Context-aware / computed filters
    assignee = django_filters.CharFilter(method="filter_assignee")
    q = django_filters.CharFilter(method="filter_q")
    created_within = django_filters.CharFilter(method="filter_created_within")
    source_ref_contains = django_filters.CharFilter(method="filter_source_ref_contains")

    class Meta:
        model = Incident
        fields = []

    def _parse_multi(self, key):
        """Accept comma-separated or repeated query params → flat list of values."""
        values = self.data.getlist(key)
        return [c.strip() for v in values for c in v.split(",") if c.strip()]

    def filter_state(self, qs, name, value):
        values = self._parse_multi("state")
        return qs.filter(state__in=values) if values else qs

    def filter_severity(self, qs, name, value):
        values = self._parse_multi("severity")
        return qs.filter(severity__in=values) if values else qs

    def filter_tlp(self, qs, name, value):
        values = self._parse_multi("tlp")
        return qs.filter(tlp__in=values) if values else qs

    def filter_assignee(self, qs, name, value):
        # Tab-level assignee constraints (my_queue/unassigned) are applied in the view
        # before the filterset runs; skip here to avoid double-filtering.
        tab = self.data.get("tab", "all")
        if tab in ("my_queue", "unassigned"):
            return qs
        if value == "me":
            if self.request:
                return qs.filter(assignee=self.request.user)
        elif value == "unassigned":
            return qs.filter(assignee__isnull=True)
        else:
            try:
                return qs.filter(assignee_id=int(value))
            except (ValueError, TypeError):
                pass
        return qs

    def filter_subject(self, qs, name, value):
        # `subject=none` is the "Unclassified" drill-down (no Subject yet); a
        # numeric value is the existing exact Subject match. Single-value only.
        if value == "none":
            return qs.filter(subject__isnull=True)
        try:
            return qs.filter(subject_id=int(value))
        except (ValueError, TypeError):
            return qs

    def filter_q(self, qs, name, value):
        return qs.filter(
            Q(title__icontains=value)
            | Q(description__icontains=value)
            | Q(display_id__icontains=value)
        )

    def filter_created_within(self, qs, name, value):
        delta = _parse_duration(value)
        if delta:
            return qs.filter(created_at__gte=timezone.now() - delta)
        return qs

    def filter_source_ref_contains(self, qs, name, value):
        try:
            ref = json.loads(value)
            if isinstance(ref, dict):
                for k, v in ref.items():
                    qs = qs.filter(**{f"source_ref__{k}": v})
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return qs


class TaskTemplateFilterSet(django_filters.FilterSet):
    subject = django_filters.NumberFilter(field_name="subject_id")

    class Meta:
        model = TaskTemplate
        fields = []


class AssetFilterSet(django_filters.FilterSet):
    org = django_filters.CharFilter(field_name="organization__slug", lookup_expr="exact")
    q = django_filters.CharFilter(field_name="name", lookup_expr="icontains")
    internet_facing = django_filters.BooleanFilter(method="filter_internet_facing")

    class Meta:
        model = Asset
        fields = []

    def filter_internet_facing(self, qs, name, value):
        from incidents.services.exposures import annotate_internet_facing
        qs = annotate_internet_facing(qs)
        return qs.filter(internet_facing=value)


class TaskFilterSet(django_filters.FilterSet):
    q = django_filters.CharFilter(field_name="title", lookup_expr="icontains")
    state = django_filters.CharFilter(field_name="state", lookup_expr="exact")
    assignee = django_filters.CharFilter(method="filter_assignee")

    class Meta:
        model = Task
        fields = []

    def filter_assignee(self, qs, name, value):
        if value == "me":
            if self.request:
                return qs.filter(assignee=self.request.user)
        elif value == "unassigned":
            return qs.filter(assignee__isnull=True)
        return qs
