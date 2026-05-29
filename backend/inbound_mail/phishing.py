"""
Pure-function phishing analysis module. No Django model instantiation here —
only lookups needed for resolve_org.
"""
import re

_SOC_RE = re.compile(r"^soc[@+]", re.IGNORECASE)

_FORWARD_INLINE_MARKERS = [
    "---------- forwarded message",
    "-----original message-----",
    "begin forwarded message",
    "-------- forwarded message --------",
    "________________________________",  # Outlook separator variant
]

_FWD_FROM_RE = re.compile(r"^from:\s*(.+)", re.IGNORECASE | re.MULTILINE)
_ANGLE_ADDR_RE = re.compile(r"<([^>]+)>")
_BARE_ADDR_RE = re.compile(r"[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}")

_FWD_PREFIX_RE = re.compile(
    r"^\s*(Fwd?|FW|Re|RE|\[EXT\]|[Aa][Ww]):?\s*",
    re.IGNORECASE,
)


def detect_forward(msg) -> bool:
    """Return True if msg structurally looks like a forwarded email."""
    for att in msg.attachments:
        if att.content_type == "message/rfc822":
            return True

    body = (msg.body_text or "").lower()
    for marker in _FORWARD_INLINE_MARKERS:
        if marker in body:
            return True
    return False


def resolve_org(from_address: str):
    """Return the Organisation for the sending user, or None."""
    from django.contrib.auth.models import User
    from api.models import UserProfile
    from security.models import OrganizationMembership

    try:
        user = User.objects.get(email__iexact=from_address)
    except User.DoesNotExist:
        return None

    try:
        profile = user.profile
        if profile.default_org_id:
            return profile.default_org
    except UserProfile.DoesNotExist:
        pass

    memberships = list(OrganizationMembership.objects.filter(user=user).select_related("organization"))
    if len(memberships) == 1:
        return memberships[0].organization
    return None


def normalise_subject(subject: str) -> str:
    """Strip forwarding/reply prefixes and return a lowercased, stripped string."""
    s = subject or ""
    prev = None
    while s != prev:
        prev = s
        s = _FWD_PREFIX_RE.sub("", s).strip()
    return s.lower().strip()


def _extract_address(text: str) -> str | None:
    """Extract the first email address from a text fragment."""
    m = _ANGLE_ADDR_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _BARE_ADDR_RE.search(text)
    if m:
        return m.group(0).strip()
    return None


def _is_excluded(address: str, forwarder_address: str) -> bool:
    if not address:
        return True
    if address.lower() == forwarder_address.lower():
        return True
    local = address.split("@")[0]
    if _SOC_RE.match(local + "@"):
        return True
    return False


def extract_original_sender(msg, forwarder_address: str) -> str | None:
    """Extract the original phishing sender address, excluding forwarder and soc@ variants."""
    for att in msg.attachments:
        if att.content_type == "message/rfc822":
            import email as _email
            try:
                inner = _email.message_from_bytes(att.payload)
                from_header = inner.get("From", "")
                addr = _extract_address(from_header)
                if addr and not _is_excluded(addr, forwarder_address):
                    return addr
            except Exception:
                pass

    body = msg.body_text or ""
    body_lower = body.lower()
    for marker in _FORWARD_INLINE_MARKERS:
        idx = body_lower.find(marker)
        if idx == -1:
            continue
        snippet = body[idx: idx + 500]
        m = _FWD_FROM_RE.search(snippet)
        if m:
            addr = _extract_address(m.group(1))
            if addr and not _is_excluded(addr, forwarder_address):
                return addr

    return None
