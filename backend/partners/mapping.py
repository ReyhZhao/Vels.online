"""Pure field-mapping engine for partner intake (ADR-0032).

`map_email_to_incident_fields(connection, message)` maps a partner's plain-text email
onto Incident fields. Per field the precedence is:

    regex capture → value_map (case-insensitive) → normalise + enum-match → field default

An empty regex skips straight to the default. No DB, no network — a pure function over
the Connection's config and the NormalisedMessage, so it is exhaustively unit-testable.
"""

import re

# Valid target-enum values, mirroring incidents.models.Incident choices. Duplicated here
# (rather than imported) to keep this module a pure, model-free function.
_ENUMS = {
    "severity": {"critical", "high", "medium", "low", "info"},
    "tlp": {"white", "green", "amber", "red"},
    "pap": {"white", "green", "amber", "red"},
}

# System fallback when neither a regex capture nor a configured default yields a value.
_SYSTEM_DEFAULTS = {"severity": "medium", "tlp": "amber", "pap": "amber"}

MAPPED_FIELDS = ("severity", "tlp", "pap", "title", "description")


def _source_text(field, message):
    """Which part of the email a field's regex runs against."""
    if field == "title":
        return message.subject or ""
    if field == "description":
        return message.body_text or ""
    # enum fields may be stated in either the subject or the body
    return f"{message.subject or ''}\n{message.body_text or ''}"


def _apply_regex(regex, text):
    """Return the first capture group (or whole match) of regex in text, else None.

    A regex that fails to compile is treated as no-match (→ falls through to default),
    never an error — a bad Connection config must not drop a real report."""
    if not regex:
        return None
    try:
        match = re.search(regex, text, re.IGNORECASE | re.DOTALL)
    except re.error:
        return None
    if not match:
        return None
    return match.group(1) if match.groups() else match.group(0)


def _default_for(field, cfg, message):
    default = (cfg.get("default") or "").strip()
    enum = _ENUMS.get(field)
    if default:
        if enum is not None:
            return default.lower() if default.lower() in enum else _SYSTEM_DEFAULTS[field]
        return default
    if field == "title":
        return (message.subject or "").strip() or "(no subject)"
    if field == "description":
        return message.body_text or ""
    return _SYSTEM_DEFAULTS.get(field, "")


def _map_one(field, cfg, message):
    cfg = cfg or {}
    captured = _apply_regex(cfg.get("regex") or "", _source_text(field, message))
    if captured is not None:
        captured = captured.strip()
        value_map = cfg.get("value_map") or {}
        if value_map:
            lowered = {str(k).lower(): v for k, v in value_map.items()}
            if captured.lower() in lowered:
                return lowered[captured.lower()]
        enum = _ENUMS.get(field)
        if enum is not None:
            if captured.lower() in enum:
                return captured.lower()
            # captured but not a valid enum value → fall through to the default
        elif captured:
            # free-text field (title/description): use the captured value directly
            return captured
    return _default_for(field, cfg, message)


def extract_external_reference(connection, message):
    """Capture the partner's External Reference from the subject, or "" if none."""
    captured = _apply_regex((connection.external_reference_regex or "").strip(), message.subject or "")
    return captured.strip() if captured else ""


def map_email_to_incident_fields(connection, message):
    """Map a partner email onto {severity, tlp, pap, title, description, external_reference}."""
    mappings = connection.field_mappings or {}
    result = {field: _map_one(field, mappings.get(field), message) for field in MAPPED_FIELDS}
    result["external_reference"] = extract_external_reference(connection, message)
    return result
