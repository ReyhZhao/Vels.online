import json

from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import mapping
from .models import CapturedPayload, IngestEndpoint, PayloadElementOutcome
from .serializers import (
    CapturedPayloadSerializer,
    IngestEndpointSerializer,
    PayloadElementOutcomeSerializer,
)

# ── Public receiver ────────────────────────────────────────────────────────────────────


class IngestReceiverView(APIView):
    """The public webhook intake at /ingest/<path_uuid>/. The UUID path is the sole credential
    (ADR-0041): no authentication, no bearer token. Guards (in order): unknown/paused → 404,
    oversize → 413, rate-limited → 429, malformed JSON → 400. Otherwise cache the body and
    return 202; mapping/materialisation happen asynchronously once the endpoint is Active."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, path_uuid):
        endpoint = (
            IngestEndpoint.objects.filter(path_uuid=path_uuid)
            .exclude(state=IngestEndpoint.STATE_PAUSED)
            .first()
        )
        if endpoint is None:
            # 404 for unknown AND paused — a prober can't tell a disabled endpoint from a typo.
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        body_bytes = request.body or b""
        if len(body_bytes) > endpoint.max_body_bytes:
            return Response(
                {"detail": "Payload too large."}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )

        if not self._within_rate_limit(endpoint):
            return Response(
                {"detail": "Rate limit exceeded."}, status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response({"detail": "Malformed JSON."}, status=status.HTTP_400_BAD_REQUEST)

        payload = CapturedPayload.objects.create(endpoint=endpoint, body=body)
        pid = payload.id
        transaction.on_commit(lambda: self._enqueue(pid))
        return Response({"captured_payload": pid}, status=status.HTTP_202_ACCEPTED)

    @staticmethod
    def _within_rate_limit(endpoint):
        limit = endpoint.rate_limit_per_minute or 0
        if limit <= 0:
            return True
        minute = int(timezone.now().timestamp() // 60)
        key = f"ingest_rl:{endpoint.id}:{minute}"
        try:
            count = cache.get_or_set(key, 0, timeout=120)
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=120)
            count = 1
        return count <= limit

    @staticmethod
    def _enqueue(payload_id):
        from .tasks import process_captured_payload

        process_captured_payload.delay(payload_id)


# ── Staff management ───────────────────────────────────────────────────────────────────


class IngestEndpointListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = IngestEndpointSerializer

    def get_queryset(self):
        qs = IngestEndpoint.objects.select_related("organization")
        target = self.request.query_params.get("target_type")
        if target:
            qs = qs.filter(target_type=target)
        return qs


class IngestEndpointDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = IngestEndpointSerializer
    queryset = IngestEndpoint.objects.select_related("organization")


class IngestEndpointRotateView(APIView):
    """Rotate the secret path — revokes the old URL (ADR-0041)."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        endpoint = get_object_or_404(IngestEndpoint, pk=pk)
        endpoint.rotate_path()
        return Response(IngestEndpointSerializer(endpoint, context={"request": request}).data)


class IngestEndpointActivateView(APIView):
    """Activate an endpoint once a mapping exists, and return a Replay preview of the backlog
    captured during the Capturing phase (offered, never automatic — CONTEXT.md → Replay)."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        from .replay import preview_endpoint

        endpoint = get_object_or_404(IngestEndpoint, pk=pk)
        if not endpoint.field_mappings:
            return Response(
                {"detail": "Define a field mapping before activating."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if endpoint.target_type == IngestEndpoint.TARGET_ALERT and not endpoint.entity_mappings:
            return Response(
                {"detail": "An Alert endpoint needs at least one ECS entity mapping."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        endpoint.state = IngestEndpoint.STATE_ACTIVE
        endpoint.save(update_fields=["state", "updated_at"])
        return Response(
            {
                "endpoint": IngestEndpointSerializer(endpoint, context={"request": request}).data,
                "replay_preview": preview_endpoint(endpoint),
            }
        )


class IngestEndpointPauseView(APIView):
    """Pause (stop ingestion, keep config/history) or resume an endpoint."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        endpoint = get_object_or_404(IngestEndpoint, pk=pk)
        resume = bool(request.data.get("resume"))
        if resume:
            endpoint.state = (
                IngestEndpoint.STATE_ACTIVE
                if endpoint.field_mappings
                else IngestEndpoint.STATE_CAPTURING
            )
        else:
            endpoint.state = IngestEndpoint.STATE_PAUSED
        endpoint.save(update_fields=["state", "updated_at"])
        return Response(IngestEndpointSerializer(endpoint, context={"request": request}).data)


class IngestEndpointDryRunView(APIView):
    """Dry-run a mapping over a Captured Payload sample (or a supplied body), returning the
    resolved element payload(s) without committing — powers the Inspector builder's live
    preview (CONTEXT.md → Field Mapping)."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        endpoint = get_object_or_404(IngestEndpoint, pk=pk)
        data = request.data or {}

        # A draft mapping may be supplied to preview unsaved edits; otherwise use the stored one.
        config = {
            "collection_root_path": data.get("collection_root_path", endpoint.collection_root_path),
            "idempotency_key_path": data.get("idempotency_key_path", endpoint.idempotency_key_path),
            "field_mappings": data.get("field_mappings", endpoint.field_mappings),
            "entity_mappings": data.get("entity_mappings", endpoint.entity_mappings),
        }

        if "body" in data:
            body = data["body"]
        else:
            captured_id = data.get("captured_payload")
            payload = get_object_or_404(CapturedPayload, pk=captured_id, endpoint=endpoint)
            body = payload.body

        resolved = mapping.resolve(config, body, endpoint.target_type)
        return Response({"elements": resolved})


class CapturedPayloadListView(generics.ListAPIView):
    """Per-endpoint Captured Payload / dead-letter list, filterable by status."""

    permission_classes = [IsAdminUser]
    serializer_class = CapturedPayloadSerializer

    def get_queryset(self):
        qs = CapturedPayload.objects.filter(endpoint_id=self.kwargs["pk"]).prefetch_related(
            "outcomes__incident", "outcomes__alert", "outcomes__asset"
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class CapturedPayloadDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = CapturedPayloadSerializer
    queryset = CapturedPayload.objects.prefetch_related(
        "outcomes__incident", "outcomes__alert", "outcomes__asset"
    )


class IngestEndpointReplayView(APIView):
    """GET previews the Replay over the covered backlog; POST executes it (CONTEXT.md → Replay)."""

    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        from .replay import preview_endpoint

        endpoint = get_object_or_404(IngestEndpoint, pk=pk)
        return Response(preview_endpoint(endpoint))

    def post(self, request, pk):
        from .replay import replay_endpoint

        endpoint = get_object_or_404(IngestEndpoint, pk=pk)
        return Response({"results": replay_endpoint(endpoint)})
