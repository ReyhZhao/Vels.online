import logging
import os

import requests

_API_URL = "https://api.uptimerobot.com/v2/getMonitors"
logger = logging.getLogger(__name__)

STATUS_MAP = {
    0: "paused",
    1: "not_checked",
    2: "up",
    8: "seems_down",
    9: "down",
}


class UptimeRobotUnavailableError(Exception):
    pass


def get_monitors(include_logs=False):
    api_key = os.environ.get("UPTIMEROBOT_API_KEY", "")
    payload = {
        "api_key": api_key,
        "format": "json",
        "custom_uptime_ratios": "7",
        "logs": 1 if include_logs else 0,
        "response_times": 1 if include_logs else 0,
    }
    try:
        response = requests.post(_API_URL, data=payload, timeout=10)
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as exc:
        logger.error("UptimeRobot API unreachable: %s", exc)
        raise UptimeRobotUnavailableError("UptimeRobot API unreachable") from exc
    response.raise_for_status()
    data = response.json()
    if data.get("stat") != "ok":
        raise RuntimeError(f"UptimeRobot API error: {data.get('error', {})}")
    return data.get("monitors", [])
