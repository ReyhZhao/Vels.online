_SEVERITY_WEIGHTS = {
    "critical": 10,
    "high": 7,
    "medium": 4,
    "low": 1,
}


def score_vulnerabilities(records):
    """
    Deduplicate, score, and rank vulnerability records.

    Each record must have: cve_id (str), severity (str), agent_count (int).
    Returns a list of dicts with the same fields plus impact_score and
    affected_agent_count, sorted by impact_score descending then cve_id ascending.
    """
    merged = {}
    for record in records:
        cve_id = record["cve_id"]
        if cve_id not in merged:
            merged[cve_id] = {"cve_id": cve_id, "severity": record["severity"], "affected_agent_count": 0}
        merged[cve_id]["affected_agent_count"] += record["agent_count"]

    scored = []
    for entry in merged.values():
        weight = _SEVERITY_WEIGHTS.get(entry["severity"], 0)
        scored.append({**entry, "impact_score": weight * entry["affected_agent_count"]})

    scored.sort(key=lambda r: (-r["impact_score"], r["cve_id"]))
    return scored
