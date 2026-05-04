import os

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_ALERTS_INDEX = "wazuh-alerts-4.x-*"
_VULNS_INDEX = "wazuh-states-vulnerabilities-wazuh"

_SEVERITY_LEVEL_RANGES = {
    "critical": {"gte": 12},
    "high":     {"gte": 8, "lt": 12},
    "medium":   {"gte": 4, "lt": 8},
    "low":      {"lt": 4},
}

_VULN_SEVERITY_LABEL = {
    "critical": "Critical",
    "high":     "High",
    "medium":   "Medium",
    "low":      "Low",
}


class OpenSearchError(RuntimeError):
    pass


class OpenSearchClient:
    def __init__(self):
        self._base_url = os.environ.get("WAZUH_INDEXER_URL", "").rstrip("/")
        self._auth = (
            os.environ.get("WAZUH_INDEXER_USER", ""),
            os.environ.get("WAZUH_INDEXER_PASSWORD", ""),
        )

    def _search(self, index, body):
        try:
            response = requests.post(
                f"{self._base_url}/{index}/_search",
                json=body,
                auth=self._auth,
                verify=False,
                timeout=15,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise OpenSearchError(f"OpenSearch error on {index}: {exc}") from exc
        return response.json()

    def get_agent_events(self, agent_id, hours=24, offset=0, limit=100, severity=None, search=""):
        filters = [
            {"term": {"agent.id": str(agent_id)}},
            {"range": {"@timestamp": {"gte": f"now-{hours}h"}}},
        ]
        if severity:
            valid = [s for s in severity if s in _SEVERITY_LEVEL_RANGES]
            if valid:
                should = [{"range": {"rule.level": _SEVERITY_LEVEL_RANGES[s]}} for s in valid]
                filters.append({"bool": {"should": should, "minimum_should_match": 1}})
        if search:
            filters.append({"match": {"rule.description": search}})
        body = {
            "query": {"bool": {"filter": filters}},
            "sort": [{"@timestamp": {"order": "desc"}}],
            "from": offset,
            "size": limit,
            "track_total_hits": True,
        }
        data = self._search(_ALERTS_INDEX, body)
        hits = data["hits"]
        return {
            "events": [{"_id": h.get("_id", ""), **h["_source"]} for h in hits["hits"]],
            "total": hits["total"]["value"],
        }

    def get_event_by_id(self, agent_id, event_id):
        body = {
            "query": {"bool": {"filter": [
                {"ids": {"values": [event_id]}},
                {"term": {"agent.id": str(agent_id)}},
            ]}},
            "size": 1,
        }
        data = self._search(_ALERTS_INDEX, body)
        hits = data["hits"]["hits"]
        if not hits:
            return None
        h = hits[0]
        return {"_id": h.get("_id", event_id), **h["_source"]}

    def get_agent_vulnerabilities(self, agent_id, offset=0, limit=50, severity=None, fix_available=None, search=""):
        filters = [{"term": {"agent.id": str(agent_id)}}]
        if severity:
            valid = [_VULN_SEVERITY_LABEL[s] for s in severity if s in _VULN_SEVERITY_LABEL]
            if valid:
                filters.append({"terms": {"vulnerability.severity": valid}})
        if fix_available is True:
            filters.append({"term": {"vulnerability.status": "Fixed"}})
        if search:
            filters.append({"multi_match": {"query": search, "fields": ["vulnerability.id", "package.name"]}})
        body = {
            "query": {"bool": {"filter": filters}},
            "from": offset,
            "size": limit,
            "track_total_hits": True,
        }
        data = self._search(_VULNS_INDEX, body)
        hits = data["hits"]
        return {
            "vulnerabilities": [{"_id": h.get("_id", ""), **h["_source"]} for h in hits["hits"]],
            "total": hits["total"]["value"],
        }

    def get_vulnerability_by_id(self, agent_id, vuln_id):
        body = {
            "query": {"bool": {"filter": [
                {"ids": {"values": [vuln_id]}},
                {"term": {"agent.id": str(agent_id)}},
            ]}},
            "size": 1,
        }
        data = self._search(_VULNS_INDEX, body)
        hits = data["hits"]["hits"]
        if not hits:
            return None
        h = hits[0]
        return {"_id": h.get("_id", vuln_id), **h["_source"]}

    def get_vulnerabilities_summary(self, agents):
        agent_ids = [a["id"] for a in agents if a.get("status") == "active"]
        if not agent_ids:
            return {"critical": 0, "high": 0, "medium": 0, "low": 0}
        body = {
            "query": {"bool": {"filter": [{"terms": {"agent.id": agent_ids}}]}},
            "aggs": {"by_severity": {"terms": {"field": "vulnerability.severity", "size": 10}}},
            "size": 0,
        }
        data = self._search(_VULNS_INDEX, body)
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for bucket in data.get("aggregations", {}).get("by_severity", {}).get("buckets", []):
            key = bucket["key"].lower()
            if key in counts:
                counts[key] = bucket["doc_count"]
        return counts

    def get_fleet_vulnerabilities(
        self, agent_ids, severity=None, fix_available=None, search=None,
        agent_id_filter=None, offset=0, limit=50, sort_by="severity", sort_order="desc",
    ):
        if not agent_ids:
            empty_stats = {"critical": 0, "high": 0, "medium": 0, "low": 0, "affected_systems": 0, "fixable": 0}
            return {"vulnerabilities": [], "total": 0, "stats": empty_stats}

        table_filters = [{"terms": {"agent.id": agent_ids}}]
        if agent_id_filter:
            table_filters.append({"term": {"agent.id": str(agent_id_filter)}})
        if severity:
            valid = [_VULN_SEVERITY_LABEL[s] for s in severity if s in _VULN_SEVERITY_LABEL]
            if valid:
                table_filters.append({"terms": {"vulnerability.severity": valid}})
        if fix_available:
            table_filters.append({"term": {"vulnerability.status": "Fixed"}})
        if search:
            table_filters.append({"multi_match": {"query": search, "fields": ["vulnerability.id", "package.name"]}})

        body = {
            "size": 0,
            "query": {"bool": {"filter": table_filters}},
            "aggs": {
                "by_cve": {
                    "terms": {"field": "vulnerability.id", "size": 10000},
                    "aggs": {
                        "severity": {"terms": {"field": "vulnerability.severity", "size": 1}},
                        "max_cvss": {"max": {"field": "vulnerability.cvss.cvss3.base_score"}},
                        "package": {"terms": {"field": "package.name", "size": 1}},
                        "affected_agents": {"cardinality": {"field": "agent.id"}},
                        "has_fix": {"filter": {"term": {"vulnerability.status": "Fixed"}}},
                        "published": {"max": {"field": "vulnerability.published"}},
                    },
                },
                "fleet_stats": {
                    "filter": {"terms": {"agent.id": agent_ids}},
                    "aggs": {
                        "affected_agents": {"cardinality": {"field": "agent.id"}},
                        "fixable_cves": {
                            "filter": {"term": {"vulnerability.status": "Fixed"}},
                            "aggs": {"unique": {"cardinality": {"field": "vulnerability.id"}}},
                        },
                        "by_severity": {"terms": {"field": "vulnerability.severity", "size": 10}},
                    },
                },
            },
        }

        data = self._search(_VULNS_INDEX, body)
        aggs = data.get("aggregations", {})
        buckets = aggs.get("by_cve", {}).get("buckets", [])

        _SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        vulns = []
        for bucket in buckets:
            sev_buckets = bucket.get("severity", {}).get("buckets", [])
            sev = sev_buckets[0]["key"].lower() if sev_buckets else "low"
            pkg_buckets = bucket.get("package", {}).get("buckets", [])
            pkg = pkg_buckets[0]["key"] if pkg_buckets else ""
            cvss = bucket.get("max_cvss", {}).get("value")
            has_fix = bucket.get("has_fix", {}).get("doc_count", 0) > 0
            published_ms = bucket.get("published", {}).get("value")
            published = None
            if published_ms:
                from datetime import datetime, timezone as dt_tz
                published = datetime.fromtimestamp(published_ms / 1000, tz=dt_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            vulns.append({
                "cve": bucket["key"],
                "severity": sev,
                "cvss_score": cvss,
                "package": pkg,
                "affected_agents": bucket.get("affected_agents", {}).get("value", 0),
                "fix_available": has_fix,
                "published": published,
            })

        if sort_by == "cvss_score":
            vulns.sort(key=lambda v: (v["cvss_score"] or 0), reverse=(sort_order == "desc"))
        elif sort_by == "affected_agents":
            vulns.sort(key=lambda v: v["affected_agents"], reverse=(sort_order == "desc"))
        elif sort_by == "published":
            vulns.sort(key=lambda v: v.get("published") or "", reverse=(sort_order == "desc"))
        else:
            vulns.sort(key=lambda v: (_SEV_ORDER.get(v["severity"], 99), -v["affected_agents"]))
            if sort_order == "asc":
                vulns.reverse()

        total = len(vulns)

        fleet = aggs.get("fleet_stats", {})
        sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for b in fleet.get("by_severity", {}).get("buckets", []):
            k = b["key"].lower()
            if k in sev_counts:
                sev_counts[k] = b["doc_count"]

        # unique CVE counts per severity from table buckets (reflects current filters if any)
        unique_sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for v in vulns:
            if v["severity"] in unique_sev:
                unique_sev[v["severity"]] += 1

        stats = {
            **unique_sev,
            "affected_systems": fleet.get("affected_agents", {}).get("value", 0),
            "fixable": fleet.get("fixable_cves", {}).get("unique", {}).get("value", 0),
        }

        return {"vulnerabilities": vulns[offset: offset + limit], "total": total, "stats": stats}

    def get_cve_detail(self, agent_ids, cve_id):
        if not agent_ids:
            return None
        body = {
            "query": {"bool": {"filter": [
                {"terms": {"agent.id": agent_ids}},
                {"term": {"vulnerability.id": cve_id}},
            ]}},
            "size": 1,
        }
        data = self._search(_VULNS_INDEX, body)
        hits = data["hits"]["hits"]
        if not hits:
            return None
        return {"_id": hits[0].get("_id", ""), **hits[0]["_source"]}

    def get_cve_affected_agents(self, agent_ids, cve_id):
        if not agent_ids:
            return []
        body = {
            "query": {"bool": {"filter": [
                {"terms": {"agent.id": agent_ids}},
                {"term": {"vulnerability.id": cve_id}},
            ]}},
            "size": 1000,
        }
        data = self._search(_VULNS_INDEX, body)
        return [{"_id": h.get("_id", ""), **h["_source"]} for h in data["hits"]["hits"]]

    def get_events_count(self, agents, hours=24):
        agent_ids = [a["id"] for a in agents if a.get("status") == "active"]
        if not agent_ids:
            return 0
        body = {
            "query": {"bool": {"filter": [
                {"terms": {"agent.id": agent_ids}},
                {"range": {"@timestamp": {"gte": f"now-{hours}h"}}},
            ]}},
            "size": 0,
            "track_total_hits": True,
        }
        data = self._search(_ALERTS_INDEX, body)
        return data["hits"]["total"]["value"]
