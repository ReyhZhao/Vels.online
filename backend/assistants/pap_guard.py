"""PAP egress guard for incident web search (ADR-0011).

PAP (Permissible Actions Protocol) governs what *actions* may be taken on the
information — and sending an incident's own indicators to an external search engine
is an action. At PAP:RED only generic research is permitted: a query that contains
one of the incident's own indicators (IOC value, asset/agent name, IP, linked
username) is blocked. Below PAP:RED (white/green/amber) there is no restriction.

This is a pure function of (query, indicators, pap_level) so it tests in isolation.
"""
import re

PAP_RED = "red"


def collect_incident_indicators(grounding: dict) -> list:
    """Pull the incident's own indicators out of its grounding payload.

    Returns lowercased literal tokens that must not leave the boundary at PAP:RED:
    IOC values, asset names, agent names, asset IPs, and linked usernames.
    """
    indicators = set()
    incident = grounding.get("incident", {}) or {}

    for ioc in grounding.get("iocs", []) or []:
        # IOC values may be annotated (e.g. "1.2.3.4 (VirusTotal: ...)") — take the
        # leading token before any whitespace/parenthesis.
        raw = str(ioc.get("value", "")).strip()
        if raw:
            indicators.add(raw.split()[0])

    for asset in grounding.get("assets", []) or []:
        for key in ("name", "agent_name", "ip_address"):
            val = asset.get(key)
            if val:
                indicators.add(str(val))

    for alert in grounding.get("linked_alerts", []) or []:
        # entity-style usernames sometimes ride along on alerts
        for key in ("user", "username", "dstuser"):
            val = alert.get(key)
            if val:
                indicators.add(str(val))

    assignee = incident.get("assignee")
    # assignee is the analyst, not an indicator — intentionally not included.

    # Drop empties and overly-short tokens that would cause false positives.
    return sorted({t.lower() for t in indicators if t and len(t) >= 3})


def check_web_search_query(query: str, indicators: list, pap_level: str) -> tuple:
    """Return (allowed: bool, reason: str).

    At PAP:RED, a query containing any indicator (case-insensitive, token-aware)
    is blocked. Otherwise allowed.
    """
    if (pap_level or "").lower() != PAP_RED:
        return True, ""

    haystack = (query or "").lower()
    for token in indicators:
        # word-ish boundary match so "ip" inside "description" doesn't trip,
        # but dotted IPs / hostnames / hashes still match as substrings.
        if re.search(r"(?<![\w.])" + re.escape(token) + r"(?![\w.])", haystack) or token in haystack:
            return False, (
                "blocked: PAP:RED forbids searching incident-specific indicators online"
            )
    return True, ""
