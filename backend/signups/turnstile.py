import requests
from django.conf import settings
from rest_framework.exceptions import ValidationError


def verify_turnstile(token, remote_ip=None):
    secret = getattr(settings, "TURNSTILE_SECRET_KEY", "")
    if not secret:
        return

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        resp = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=payload,
            timeout=5,
        )
        data = resp.json()
    except Exception as exc:
        raise ValidationError("Bot protection check failed. Please try again.") from exc

    if not data.get("success"):
        raise ValidationError("Bot protection check failed. Please try again.")
