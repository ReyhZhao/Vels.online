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
            "vulnerabilities": [h["_source"] for h in hits["hits"]],
            "total": hits["total"]["value"],
        }

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
