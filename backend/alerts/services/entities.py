import re

ECS_FIELDS = frozenset({
    "host.name",
    "source.ip",
    "user.name",
    "file.hash.sha256",
    "process.name",
})

_DOMAIN_BACKSLASH_RE = re.compile(r"^[^\\]+\\(.+)$")
_DOMAIN_AT_RE = re.compile(r"^(.+)@[^@]+$")


def canonicalize(field: str, value: str) -> str:
    """Return a normalised entity value for the given ECS field.

    All values are case-folded.  For user.name the three common formats
    (DOMAIN\\user, user@domain, user) are all collapsed to the bare username.
    """
    v = value.strip().casefold()
    if field == "user.name":
        m = _DOMAIN_BACKSLASH_RE.match(v)
        if m:
            return m.group(1)
        m = _DOMAIN_AT_RE.match(v)
        if m:
            return m.group(1)
    return v


def entities_for(payload: dict) -> list[tuple[str, str]]:
    """Extract (entity_type, canonical_value) pairs from an alert payload.

    Reads the top-level ``entities`` key which must be a dict keyed by ECS
    field names.  Unknown keys are silently ignored.  Returns an empty list
    when the envelope is absent or empty.
    """
    envelope = payload.get("entities")
    if not isinstance(envelope, dict):
        return []
    result = []
    for field, raw in envelope.items():
        if field not in ECS_FIELDS:
            continue
        if not raw or not isinstance(raw, str):
            continue
        result.append((field, canonicalize(field, raw)))
    return result
