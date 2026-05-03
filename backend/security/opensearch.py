import os

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_ALERTS_INDEX = "wazuh-alerts-4.x-*"
_VULNS_INDEX = "wazuh-states-vulnerabilities-wazuh"


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

    def get_agent_events(self, agent_id, hours=24, offset=0, limit=100):
        body = {
            "query": {"bool": {"filter": [
                {"term": {"agent.id": str(agent_id)}},
                {"range": {"@timestamp": {"gte": f"now-{hours}h"}}},
            ]}},
            "sort": [{"@timestamp": {"order": "desc"}}],
            "from": offset,
            "size": limit,
            "track_total_hits": True,
        }
        data = self._search(_ALERTS_INDEX, body)
        hits = data["hits"]
        return {
            "events": [h["_source"] for h in hits["hits"]],
            "total": hits["total"]["value"],
        }

    def get_agent_vulnerabilities(self, agent_id, offset=0, limit=50):
        body = {
            "query": {"bool": {"filter": [
                {"term": {"agent.id": str(agent_id)}},
            ]}},
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
