"""Sender-auth verification for partner intake (ADR-0032).

Partner trust is "believe the From address", made safe by DKIM/SPF verification. A pure
`verify_message_auth(raw_message)` parses the message's `Authentication-Results` header
(stamped by the receiving mail path) for a DKIM pass and an SPF pass. Gated by the env
var `PARTNER_INTAKE_VERIFY_AUTH` (default on); when off it always passes, for environments
whose mail path cannot stamp `Authentication-Results`.

Pure: parses headers only, no DB and no network.
"""

import email
import logging
import os
import re

logger = logging.getLogger(__name__)

_DKIM_PASS = re.compile(r"\bdkim\s*=\s*pass\b", re.IGNORECASE)
_SPF_PASS = re.compile(r"\bspf\s*=\s*pass\b", re.IGNORECASE)


def verification_enabled():
    return os.environ.get("PARTNER_INTAKE_VERIFY_AUTH", "1").strip().lower() not in (
        "0", "false", "no", "off", "",
    )


def verify_message_auth(raw_message):
    """Return True if the message passes sender-auth (DKIM pass AND SPF pass), or if
    verification is disabled. Returns False when enabled and the header is missing or
    does not show both passing."""
    if not verification_enabled():
        return True
    if not raw_message:
        return False
    try:
        if isinstance(raw_message, bytes):
            parsed = email.message_from_bytes(raw_message)
        else:
            parsed = email.message_from_string(str(raw_message))
    except Exception:
        logger.warning("partner: could not parse raw message for auth verification")
        return False

    results = " ".join(parsed.get_all("Authentication-Results") or [])
    if not results:
        return False
    return bool(_DKIM_PASS.search(results)) and bool(_SPF_PASS.search(results))
