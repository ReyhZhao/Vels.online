"""Incident trend aggregation.

A pure-ish data transformation: take an already tenant-scoped / filtered
``Incident`` queryset and bucket it into one entry per day across a window,
broken down by **Subject** (the triage classification — see ``CONTEXT.md``).

The interesting logic lives here and is exercised directly, with no HTTP or
filter machinery:

  * one bucket per day across the window, including empty days, so the time
    axis is continuous;
  * the **top N Subjects by total count in the window** render as distinct
    series; every remaining real Subject collapses into a synthetic **"Other"**
    series; incidents with no Subject fold into a synthetic **"Unclassified"**
    series;
  * "Other" and "Unclassified" carry no ``subject_id`` so the frontend can tell
    them apart from real Subjects and apply the click-to-filter rules;
  * deterministic tie-breaking at the N boundary (by name, then id) so output
    is stable.
"""
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

OTHER_KEY = "other"
UNCLASSIFIED_KEY = "unclassified"

DEFAULT_TOP_N = 7


def compute_incident_trend(queryset, days, top_n=DEFAULT_TOP_N, now=None):
    """Aggregate ``queryset`` into daily Subject buckets over the last ``days``.

    Returns::

        {
          "days": 30,
          "start": "2026-05-27",
          "end": "2026-06-25",
          "buckets": [
            {"date": "2026-05-27", "counts": {"3": 2, "other": 1, "unclassified": 4}},
            ...                                       # one per day, empty days too
          ],
          "subjects": [
            {"key": "3", "subject_id": 3, "name": "Brute Force", "kind": "real"},
            {"key": "other", "subject_id": None, "name": "Other", "kind": "other"},
            {"key": "unclassified", "subject_id": None, "name": "Unclassified", "kind": "unclassified"},
          ],
        }

    ``subjects`` is ordered: real Subjects by descending window total (ties
    broken by name then id), then "Other", then "Unclassified" — but each
    synthetic series is only present when it actually has incidents.
    """
    now = now or timezone.now()
    end = timezone.localdate(now)
    start = end - timedelta(days=days - 1)

    windowed = queryset.filter(created_at__date__gte=start, created_at__date__lte=end)

    rows = (
        windowed
        .annotate(day=TruncDate("created_at"))
        .values("day", "subject_id", "subject__name")
        .annotate(count=Count("id"))
    )

    # Window totals per real Subject (subject_id is None ⇒ Unclassified).
    totals = {}          # subject_id -> total count
    names = {}           # subject_id -> display name
    unclassified_total = 0
    for row in rows:
        sid = row["subject_id"]
        cnt = row["count"]
        if sid is None:
            unclassified_total += cnt
            continue
        totals[sid] = totals.get(sid, 0) + cnt
        names[sid] = row["subject__name"]

    # Deterministic top-N selection: most incidents first, ties broken by name
    # then id so the output never depends on DB row ordering.
    ranked = sorted(totals, key=lambda sid: (-totals[sid], names[sid], sid))
    top_ids = set(ranked[:top_n])
    has_other = len(ranked) > top_n

    # Build the ordered series list.
    subjects = [
        {"key": str(sid), "subject_id": sid, "name": names[sid], "kind": "real"}
        for sid in ranked[:top_n]
    ]
    if has_other:
        subjects.append(
            {"key": OTHER_KEY, "subject_id": None, "name": "Other", "kind": "other"}
        )
    if unclassified_total:
        subjects.append(
            {"key": UNCLASSIFIED_KEY, "subject_id": None, "name": "Unclassified", "kind": "unclassified"}
        )

    def series_key(sid):
        if sid is None:
            return UNCLASSIFIED_KEY
        return str(sid) if sid in top_ids else OTHER_KEY

    # Empty bucket per day across the whole window.
    buckets = {}
    cursor = start
    while cursor <= end:
        buckets[cursor] = {"date": cursor.isoformat(), "counts": {}}
        cursor += timedelta(days=1)

    for row in rows:
        bucket = buckets[row["day"]]["counts"]
        key = series_key(row["subject_id"])
        bucket[key] = bucket.get(key, 0) + row["count"]

    return {
        "days": days,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "buckets": [buckets[d] for d in sorted(buckets)],
        "subjects": subjects,
    }
