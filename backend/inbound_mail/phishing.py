"""
Pure-function phishing analysis module. No Django model instantiation here —
only lookups needed for resolve_org.
"""
import email.utils
import html as _html_module
import re

_SOC_RE = re.compile(r"^soc[@+]", re.IGNORECASE)

# Text-body inline-forward markers (lowercased for comparison)
_FORWARD_INLINE_MARKERS = [
    "---------- forwarded message",
    "-----original message-----",
    "begin forwarded message",
    "-------- forwarded message --------",
    "________________________________",  # Outlook separator variant
    "forwarded message",                 # generic fallback
]

# HTML-specific markers written by common mail clients
_HTML_FORWARD_MARKERS = [
    'class="gmail_quote"',      # Gmail
    "class='gmail_quote'",
    'class="gmail_attr"',       # Gmail attribution line
    'type="cite"',              # Apple Mail <blockquote type="cite">
    "type='cite'",
    'id="divRplyFwdMsg"',       # Outlook Web
    "id='divrplyfwdmsg'",       # Outlook Web (lowercased variant)
    'id="OLK_SRC_BODY_SECTION"',  # Outlook desktop
]

# Matches a "Fwd:" / "Fw:" subject prefix (not Re:, which isn't a forward)
_SUBJECT_FWD_RE = re.compile(r"^\s*Fwd?:", re.IGNORECASE)

_FWD_FROM_RE = re.compile(r"^\s*from:\s*(.+)", re.IGNORECASE | re.MULTILINE)
_HTML_TAG_RE = re.compile(r"<[^@>]+>")
# Block/line elements that should become newlines, not spaces, when stripped
_HTML_NEWLINE_RE = re.compile(
    r"<(?:br|p|div|blockquote|tr|td|th|h[1-6]|li)[^@>]*>", re.IGNORECASE
)
_ANGLE_ADDR_RE = re.compile(r"<([^>]+)>")
_BARE_ADDR_RE = re.compile(r"[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}")

_FWD_PREFIX_RE = re.compile(
    r"^\s*(Fwd?|FW|Re|RE|\[EXT\]|[Aa][Ww]):?\s*",
    re.IGNORECASE,
)


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text: block elements → newlines, other tags stripped, entities unescaped."""
    text = _HTML_NEWLINE_RE.sub("\n", html)
    text = _HTML_TAG_RE.sub(" ", text)
    return _html_module.unescape(text)


def _bare_address(raw: str) -> str:
    """Return the bare email address from a possibly 'Name <addr>' string."""
    _, addr = email.utils.parseaddr(raw or "")
    return (addr or raw or "").lower().strip()


def detect_forward(msg) -> bool:
    """Return True if msg structurally looks like a forwarded email."""
    # 1. RFC 822 attachment — most reliable signal
    for att in msg.attachments:
        if att.content_type == "message/rfc822":
            return True

    # 2. Subject prefix — "Fwd:" / "Fw:" is unambiguous
    if _SUBJECT_FWD_RE.match(msg.subject or ""):
        return True

    # 3. Text body inline-forward markers
    body_text = (msg.body_text or "").lower()
    for marker in _FORWARD_INLINE_MARKERS:
        if marker in body_text:
            return True

    # 4. HTML body — check structural markers first, then strip tags and re-scan
    body_html = (msg.body_html or "").lower()
    if body_html:
        for marker in _HTML_FORWARD_MARKERS:
            if marker in body_html:
                return True
        # Convert to plain text and scan for inline markers
        stripped = _html_to_text(body_html)
        for marker in _FORWARD_INLINE_MARKERS:
            if marker in stripped:
                return True

    return False


def resolve_org(from_address: str):
    """Return the Organisation for the sending user, or None."""
    from django.contrib.auth.models import User
    from api.models import UserProfile
    from security.models import OrganizationMembership

    bare = _bare_address(from_address)
    try:
        user = User.objects.get(email__iexact=bare)
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
    # Compare bare addresses so "Name <addr>" and "addr" both match
    if _bare_address(address) == _bare_address(forwarder_address):
        return True
    local = address.split("@")[0]
    if _SOC_RE.match(local + "@"):
        return True
    return False


def extract_original_sender(msg, forwarder_address: str) -> str | None:
    """Extract the original phishing sender address, excluding forwarder and soc@ variants."""
    # 1. RFC 822 attachment From: header
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

    # 2. Text body — scan after each inline-forward marker
    body = msg.body_text or ""
    addr = _scan_body_for_sender(body, forwarder_address)
    if addr:
        return addr

    # 3. HTML body — convert to plain text then scan
    if msg.body_html:
        addr = _scan_body_for_sender(_html_to_text(msg.body_html), forwarder_address)
        if addr:
            return addr

    return None


def _scan_body_for_sender(body: str, forwarder_address: str) -> str | None:
    """Scan plain text for a From: line after a forward marker, or anywhere in the body."""
    body_lower = body.lower()

    # First pass: anchored to a known forward marker
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

    # Second pass: no marker — search the whole body for the first From: line
    # that isn't the forwarder (handles clients that don't add a separator)
    for m in _FWD_FROM_RE.finditer(body):
        addr = _extract_address(m.group(1))
        if addr and not _is_excluded(addr, forwarder_address):
            return addr

    return None
