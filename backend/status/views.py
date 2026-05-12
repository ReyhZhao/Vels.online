import datetime
import logging

from django.core.cache import cache
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MonitorVisibility
from .serializers import MonitorVisibilityPatchSerializer
from .uptimerobot import STATUS_MAP, UptimeRobotUnavailableError, get_monitors

logger = logging.getLogger(__name__)

_CACHE_KEY = "uptimerobot_monitors"
_CACHE_TTL = 300  # 5 minutes

_LOG_TYPE_MAP = {1: "down", 2: "up", 98: "started", 99: "paused"}


def _format_logs(raw_logs):
    result = []
    for log in raw_logs or []:
        result.append({
            "datetime": datetime.datetime.fromtimestamp(
                log["datetime"], tz=datetime.timezone.utc
            ).isoformat(),
            "type": _LOG_TYPE_MAP.get(log.get("type"), "unknown"),
            "duration_seconds": log.get("duration"),
        })
    return result


def _build_monitor_entry(m, include_logs=False):
    entry = {
        "name": m["friendly_name"],
        "status": STATUS_MAP.get(m["status"], "unknown"),
        "uptime_ratio": m.get("custom_uptime_ratio"),
        "response_time": m.get("average_response_time"),
    }
    if include_logs:
        entry["logs"] = _format_logs(m.get("logs"))
    return entry


def _get_visible_ids():
    return set(
        MonitorVisibility.objects.filter(is_visible=True).values_list("monitor_id", flat=True)
    )


class StatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        is_admin = request.user.is_authenticated and request.user.is_staff

        if not is_admin:
            cached = cache.get(_CACHE_KEY)
            if cached is not None:
                return Response(cached)

        try:
            monitors = get_monitors(include_logs=is_admin)
        except UptimeRobotUnavailableError:
            logger.error("Status endpoint returning 503: UptimeRobot unavailable")
            return Response({"error": "upstream_unavailable"}, status=503)

        visible_ids = _get_visible_ids()
        visible = [m for m in monitors if str(m["id"]) in visible_ids]

        result = [_build_monitor_entry(m, include_logs=is_admin) for m in visible]

        if not is_admin:
            cache.set(_CACHE_KEY, result, _CACHE_TTL)

        return Response(result)


class MonitorListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        raw_monitors = get_monitors()
        visibility_map = {
            mv.monitor_id: mv
            for mv in MonitorVisibility.objects.all()
        }

        result = [
            {
                "monitor_id": str(m["id"]),
                "name": m["friendly_name"],
                "is_visible": visibility_map[str(m["id"])].is_visible
                if str(m["id"]) in visibility_map
                else False,
            }
            for m in raw_monitors
        ]
        return Response(result)


class MonitorDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, monitor_id):
        serializer = MonitorVisibilityPatchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data
        obj, _ = MonitorVisibility.objects.update_or_create(
            monitor_id=monitor_id,
            defaults={"name": data["name"], "is_visible": data["is_visible"]},
        )
        return Response({"monitor_id": obj.monitor_id, "name": obj.name, "is_visible": obj.is_visible})


class StatusRefreshView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        cache.delete(_CACHE_KEY)

        monitors = get_monitors(include_logs=True)
        visible_ids = _get_visible_ids()
        visible = [m for m in monitors if str(m["id"]) in visible_ids]

        cache.set(_CACHE_KEY, [_build_monitor_entry(m) for m in visible], _CACHE_TTL)

        return Response([_build_monitor_entry(m, include_logs=True) for m in visible])
