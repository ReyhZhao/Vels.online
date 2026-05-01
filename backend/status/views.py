import datetime

from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import MonitorVisibility
from .uptimerobot import STATUS_MAP, get_monitors

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


@api_view(["GET"])
@permission_classes([AllowAny])
def status_view(request):
    is_admin = request.user.is_authenticated and request.user.is_staff

    if not is_admin:
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            return Response(cached)

    monitors = get_monitors(include_logs=is_admin)
    visible_ids = _get_visible_ids()
    visible = [m for m in monitors if str(m["id"]) in visible_ids]

    result = [_build_monitor_entry(m, include_logs=is_admin) for m in visible]

    if not is_admin:
        cache.set(_CACHE_KEY, result, _CACHE_TTL)

    return Response(result)


@api_view(["GET"])
@permission_classes([AllowAny])
def monitors_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return Response(status=403)

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
            else True,
        }
        for m in raw_monitors
    ]
    return Response(result)


@api_view(["PATCH"])
@permission_classes([AllowAny])
def monitor_detail_view(request, monitor_id):
    if not (request.user.is_authenticated and request.user.is_staff):
        return Response(status=403)

    name = request.data.get("name", "")
    is_visible = request.data.get("is_visible")
    if is_visible is None:
        return Response({"detail": "is_visible is required."}, status=400)

    obj, _ = MonitorVisibility.objects.update_or_create(
        monitor_id=monitor_id,
        defaults={"name": name, "is_visible": is_visible},
    )
    return Response({"monitor_id": obj.monitor_id, "name": obj.name, "is_visible": obj.is_visible})


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_view(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return Response(status=403)

    cache.delete(_CACHE_KEY)

    monitors = get_monitors(include_logs=True)
    visible_ids = _get_visible_ids()
    visible = [m for m in monitors if str(m["id"]) in visible_ids]

    cache.set(_CACHE_KEY, [_build_monitor_entry(m) for m in visible], _CACHE_TTL)

    return Response([_build_monitor_entry(m, include_logs=True) for m in visible])
