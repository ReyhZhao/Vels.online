"""Match a Route's backend_host to a host Asset (PRD #536).

Pure function over (route, candidate_assets) — no DB queries, fully unit-testable.

Rules:
- netbird routes: no auto-match, no suggestion (overlay IPs won't match Wazuh addresses).
- Exactly one candidate whose ip_address equals route.backend_host → auto_match.
- Zero or multiple IP matches → no auto_match.
- Candidates where agent_name or name equals backend_host → suggestions (never auto-linked).
"""
from typing import List, Optional, Tuple


def match_backend_to_asset(route, candidate_assets) -> Tuple[Optional[object], List[object]]:
    if route.backend_type == "netbird":
        return None, []

    ip_matches = [
        a for a in candidate_assets
        if a.ip_address and str(a.ip_address) == route.backend_host
    ]

    auto_match = ip_matches[0] if len(ip_matches) == 1 else None

    suggestions = [
        a for a in candidate_assets
        if a not in ip_matches
        and (a.agent_name == route.backend_host or a.name == route.backend_host)
    ]

    return auto_match, suggestions
