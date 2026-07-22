"""Aggregated platform statistics for the public landing page.

Unauthenticated by design — this feeds the marketing front door at `/`. Only
whole-platform counts are exposed: no organisation names, no per-tenant
breakdown, nothing that identifies a customer. The numbers are cached so a
burst of visitors costs one set of queries, and throttled per IP so the
endpoint cannot be used to hammer the database.
"""

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

CACHE_KEY = "public:platform_stats:v1"
CACHE_TTL_SECONDS = 15 * 60

# Rolling window the "last 30 days" figures are counted over.
WINDOW_DAYS = 30


class PublicStatsThrottle(AnonRateThrottle):
    scope = "public_stats"
    rate = "60/hour"


def compute_stats():
    """Run the aggregate queries. Callers should prefer the cached view."""
    from alerts.models import Alert
    from correlations.models import CorrelationRule, SearchRule
    from incidents.models import Asset, Incident
    from security.models import Organization

    cutoff = timezone.now() - timedelta(days=WINDOW_DAYS)

    # Incident has no closed_at column, so "resolved in the window" is
    # approximated by its last update. Good enough for a headline figure; if
    # this ever needs to be exact, add a closed_at and count on that instead.
    resolved_states = [Incident.STATE_RESOLVED, Incident.STATE_CLOSED]

    return {
        "window_days": WINDOW_DAYS,
        "alerts_ingested": Alert.objects.filter(created_at__gte=cutoff).count(),
        "incidents_resolved": Incident.objects.filter(
            state__in=resolved_states, updated_at__gte=cutoff
        ).count(),
        "endpoints_monitored": Asset.objects.filter(
            kind=Asset.KIND_HOST, is_active=True
        ).count(),
        # The Infrastructure pseudo-org (ADR-0017) owns no customer, so counting
        # it here would overstate the tenant count on a public page.
        "organizations_protected": Organization.objects.filter(
            is_infrastructure=False
        ).count(),
        "detection_rules_live": (
            CorrelationRule.objects.filter(enabled=True).count()
            + SearchRule.objects.filter(enabled=True).count()
        ),
        "generated_at": timezone.now().isoformat(),
    }


class PublicStatsView(APIView):
    """GET /api/public/stats/ — cached, throttled, anonymous."""

    # No authentication at all: the endpoint is public, and dropping session auth
    # means the per-IP throttle applies to every caller rather than only to
    # logged-out ones.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicStatsThrottle]

    def get(self, request):
        stats = cache.get(CACHE_KEY)
        if stats is None:
            stats = compute_stats()
            cache.set(CACHE_KEY, stats, CACHE_TTL_SECONDS)
        return Response(stats)
