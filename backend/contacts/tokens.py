import os

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner


def _expiry_days():
    return int(os.environ.get("CONTACT_REPLY_TOKEN_EXPIRY_DAYS", 30))


def _signer():
    return TimestampSigner(salt="contact_reply")


def sign_contact_reply_token(incident_id, contact_id):
    return _signer().sign(f"{incident_id}:{contact_id}")


def unsign_contact_reply_token(token):
    max_age = _expiry_days() * 86400
    value = _signer().unsign(token, max_age=max_age)
    incident_id, contact_id = value.split(":")
    return int(incident_id), int(contact_id)


def build_reply_to_address(incident_id, contact_id):
    token = sign_contact_reply_token(incident_id, contact_id)
    domain = os.environ.get("INBOUND_REPLY_DOMAIN") or _default_domain()
    return f"soc+{token}@{domain}"


def _default_domain():
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    if "@" in from_email:
        return from_email.split("@", 1)[1].rstrip(">").strip()
    return "vels.online"
