import json
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from alerts.models import Alert, AlertEntity
from correlations.models import (
    ALERT_FIELD_CATALOG,
    CORRELATION_KEY_CHOICES,
    ENTITY_CATALOG,
    FIELD_KIND_ALERT,
    FIELD_KIND_ENTITY,
    FIELD_KIND_SOURCE_REF,
    SOURCE_REF_CATALOG,
)
from security.models import Organization

_FIELD_CATALOG = {
    FIELD_KIND_ALERT: sorted(ALERT_FIELD_CATALOG),
    FIELD_KIND_ENTITY: sorted(ENTITY_CATALOG),
    FIELD_KIND_SOURCE_REF: sorted(SOURCE_REF_CATALOG),
}

_ALLOWED_OPERATORS = {
    FIELD_KIND_ALERT: sorted({"equals", "in", "contains", "gte", "lte"}),
    FIELD_KIND_ENTITY: sorted({"equals", "in", "contains", "cidr"}),
    FIELD_KIND_SOURCE_REF: sorted({"equals", "in", "contains"}),
}


def _bounds():
    return (
        int(getattr(settings, "GROUNDING_WINDOW_DAYS", 30)),
        int(getattr(settings, "GROUNDING_VALUE_CAP", 50)),
        int(getattr(settings, "GROUNDING_SAMPLE_CAP", 15)),
    )


def _org_for_scope(scope):
    """Return an Organization instance for a slug scope, or None if not found."""
    try:
        return Organization.objects.get(slug=scope)
    except Organization.DoesNotExist:
        return None


def _alert_qs(scope, since):
    qs = Alert.objects.filter(created_at__gte=since)
    if scope and scope != "all":
        org = _org_for_scope(scope)
        if org is None:
            return Alert.objects.none()
        qs = qs.filter(organization=org)
    return qs


def _entity_qs(scope, since):
    qs = AlertEntity.objects.filter(alert__created_at__gte=since)
    if scope and scope != "all":
        org = _org_for_scope(scope)
        if org is None:
            return AlertEntity.objects.none()
        qs = qs.filter(organization=org)
    return qs


def build_grounding(scope=None, now=None) -> dict:
    """Build full alert-grounded payload for the given scope."""
    if now is None:
        now = timezone.now()

    window_days, value_cap, sample_cap = _bounds()
    since = now - timedelta(days=window_days)

    alert_qs = _alert_qs(scope, since)
    entity_qs = _entity_qs(scope, since)

    # Source kinds with counts
    source_kinds = {
        row["source_kind"]: row["count"]
        for row in alert_qs.values("source_kind").annotate(count=Count("id")).order_by("-count")
    }

    # Severity distribution
    severity_distribution = {
        row["severity"]: row["count"]
        for row in alert_qs.exclude(severity__isnull=True)
        .values("severity")
        .annotate(count=Count("id"))
    }

    # Top concrete values per alert field
    alert_top_values = {}
    for field_name in ALERT_FIELD_CATALOG:
        rows = (
            alert_qs.exclude(**{f"{field_name}__isnull": True})
            .exclude(**{f"{field_name}": ""})
            .values(field_name)
            .annotate(count=Count("id"))
            .order_by("-count")[:value_cap]
        )
        vals = [row[field_name] for row in rows]
        if vals:
            alert_top_values[field_name] = vals

    # Entity types actually populated + top values per type
    entity_types = sorted(entity_qs.values_list("entity_type", flat=True).distinct())
    entity_top_values = {}
    for et in entity_types:
        rows = (
            entity_qs.filter(entity_type=et)
            .values("value")
            .annotate(count=Count("id"))
            .order_by("-count")[:value_cap]
        )
        entity_top_values[et] = [row["value"] for row in rows]

    # Source-ref keys actually present + top values per key
    # Iterate a bounded slice in Python since source_ref is a JSONField
    sr_scan_limit = value_cap * 4
    source_ref_dicts = list(
        alert_qs.exclude(source_ref={})
        .values_list("source_ref", flat=True)[:sr_scan_limit]
    )
    sr_values: dict = {}
    for sr in source_ref_dicts:
        if not isinstance(sr, dict):
            continue
        for k, v in sr.items():
            if k not in sr_values:
                sr_values[k] = []
            if v is not None and str(v).strip():
                sr_values[k].append(str(v))

    source_ref_top_values = {}
    for k, vs in sr_values.items():
        seen: dict = {}
        deduped = []
        for v in vs:
            if v not in seen:
                seen[v] = True
                deduped.append(v)
            if len(deduped) >= value_cap:
                break
        source_ref_top_values[k] = deduped

    source_ref_keys = list(source_ref_top_values.keys())

    # Sample alert records (most recent first)
    samples = list(alert_qs.prefetch_related("entities").order_by("-created_at")[:sample_cap])
    sample_alerts = []
    for alert in samples:
        entities: dict = {}
        for e in alert.entities.all():
            if e.entity_type not in entities:
                entities[e.entity_type] = []
            entities[e.entity_type].append(e.value)
        sample_alerts.append({
            "source_kind": alert.source_kind,
            "severity": alert.severity,
            "title": alert.title,
            "source_ref": alert.source_ref,
            "entities": entities,
        })

    return {
        "field_catalog": _FIELD_CATALOG,
        "allowed_operators": _ALLOWED_OPERATORS,
        "severities": ["critical", "high", "medium", "low", "info"],
        "correlation_keys": [k for k, _ in CORRELATION_KEY_CHOICES],
        "source_kinds": source_kinds,
        "severity_distribution": severity_distribution,
        "entity_types": entity_types,
        "source_ref_keys": source_ref_keys,
        "top_values": {
            "alert_field": alert_top_values,
            "entity": entity_top_values,
            "source_ref": source_ref_top_values,
        },
        "sample_alerts": sample_alerts,
    }
