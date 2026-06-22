"""Live Attack Map API (PRD #594, ADR-0027).

Staff-only. A reconnectable SSE tail of the shared Redis attack buffer, mirroring the
Hunt stream (`hunts/views.py`): backfill the buffer on connect (``?after=-1``), then
tail ``seq > after`` emitting ``arc`` events plus a periodic ``stats`` blob for the
side panels. Each loop refreshes this connection's presence heartbeat so the producer
keeps querying while at least one map is open and stops when the last one closes.

Plus a tiny staff-only config endpoint for the global severity floor (slice #600).
"""
import asyncio
import json
import logging
import uuid

from adrf.views import APIView as AsyncAPIView
from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import presence
from .buffer import AttackBuffer
from .config import get_severity_floor, set_severity_floor

logger = logging.getLogger(__name__)

# Cadence of the SSE tail loop and how often a stats blob is re-emitted.
_LOOP_SLEEP = 1.0
_STATS_EVERY = 5          # loops (~5s)
_IDLE_LOOP_LIMIT = 1800   # ~30 min safety bound on an abandoned socket


def _arc_payload(entry: dict) -> dict:
    """Map a stored (snake_case) Attack to the camelCase SSE arc wire shape."""
    return {
        "seq": entry["seq"],
        "ts": entry.get("ts"),
        "level": entry.get("level"),
        "color": entry.get("color"),
        "attackType": entry.get("attack_type"),
        "srcCountry": entry.get("src_country"),
        "srcLat": entry.get("src_lat"),
        "srcLng": entry.get("src_lng"),
        "dstOrg": entry.get("dst_org_label"),
        "dstLat": entry.get("dst_lat"),
        "dstLng": entry.get("dst_lng"),
    }


class AttackStreamView(AsyncAPIView):
    """Reconnectable SSE tail of the shared attack buffer. Staff-only."""

    schema = None

    async def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)

        try:
            after = int(request.query_params.get("after", -1))
        except (TypeError, ValueError):
            after = -1

        conn_id = uuid.uuid4().hex
        buf = AttackBuffer()

        since = sync_to_async(buf.since)
        get_stats = sync_to_async(buf.get_stats)
        beat = sync_to_async(presence.heartbeat)
        drop = sync_to_async(presence.drop)

        async def event_stream():
            last = after
            loops = 0
            idle = 0
            try:
                # Register presence immediately so the producer starts on first connect.
                await beat(conn_id)
                # Cold-join backfill: paint recent history before tailing live.
                stats = await get_stats()
                if stats:
                    yield f"event: stats\ndata: {json.dumps(stats)}\n\n"
                for entry in await since(last):
                    last = entry["seq"]
                    yield f"event: arc\ndata: {json.dumps(_arc_payload(entry))}\n\n"

                while True:
                    await beat(conn_id)
                    rows = await since(last)
                    for entry in rows:
                        last = entry["seq"]
                        yield f"event: arc\ndata: {json.dumps(_arc_payload(entry))}\n\n"
                    loops += 1
                    if loops % _STATS_EVERY == 0:
                        stats = await get_stats()
                        if stats:
                            yield f"event: stats\ndata: {json.dumps(stats)}\n\n"
                    if rows:
                        idle = 0
                    else:
                        idle += 1
                        if idle > _IDLE_LOOP_LIMIT:
                            return
                    await asyncio.sleep(_LOOP_SLEEP)
            finally:
                await drop(conn_id)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["X-Accel-Buffering"] = "no"
        response["Cache-Control"] = "no-cache"
        return response


class AttackMapConfigView(APIView):
    """GET / PUT the global severity floor (slice #600). Staff-only, live (no redeploy)."""

    def _denied(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        return None

    def get(self, request):
        denied = self._denied(request)
        if denied:
            return denied
        return Response({"severity_floor": get_severity_floor()})

    def put(self, request):
        denied = self._denied(request)
        if denied:
            return denied
        try:
            floor = int(request.data.get("severity_floor"))
        except (TypeError, ValueError):
            return Response({"detail": "severity_floor must be an integer."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not 0 <= floor <= 15:
            return Response({"detail": "severity_floor must be between 0 and 15."},
                            status=status.HTTP_400_BAD_REQUEST)
        set_severity_floor(floor)
        return Response({"severity_floor": get_severity_floor()})
