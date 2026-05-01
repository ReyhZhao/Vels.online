import os

import requests

_API_URL = "https://api.uptimerobot.com/v2/getMonitors"

STATUS_MAP = {
    0: "paused",
    1: "not_checked",
    2: "up",
    8: "seems_down",
    9: "down",
}


def get_monitors(include_logs=False):
    api_key = os.environ.get("UPTIMEROBOT_API_KEY", "")
    payload = {
        "api_key": api_key,
        "format": "json",
        "custom_uptime_ratios": "7",
        "logs": 1 if include_logs else 0,
        "response_times": 1 if include_logs else 0,
    }
    response = requests.post(_API_URL, data=payload, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("stat") != "ok":
        raise RuntimeError(f"UptimeRobot API error: {data.get('error', {})}")
    return data.get("monitors", [])
