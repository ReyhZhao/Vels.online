import json
import os
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_ALERTS_INDEX = "wazuh-alerts-4.x-*"
_VULNS_INDEX = "wazuh-states-vulnerabilities-wazuh"

_MAPPING_TTL = 300  # seconds
_RULE_CATALOG_TTL = 300

_field_mapping_cache: dict = {}  # {"ts": float, "data": dict}
_rule_catalog_cache: dict = {}   # {cache_key: {"ts": float, "data": dict}}


def _flatten_mapping(properties: dict, prefix: str, result: dict) -> None:
    """Recursively flatten OpenSearch field properties into {dot.path: type}."""
    for name, defn in properties.items():
        path = f"{prefix}.{name}" if prefix else name
        if "type" in defn:
            result[path] = defn["type"]
        sub_props = defn.get("properties")
        if sub_props:
            _flatten_mapping(sub_props, path, result)

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

    def get_raw_mapping(self) -> dict:
        """Return the alerts index's raw mappings body ({"properties": {...}, ...}).

        Unlike get_field_mapping (which flattens to {path: type}), this returns the nested
        mapping suitable for re-applying when creating an index — used by the Rule Test
        sandbox to clone the live alerts mapping onto its ephemeral test index (ADR-0010).
        """
        try:
            response = requests.get(
                f"{self._base_url}/{_ALERTS_INDEX}/_mapping",
                auth=self._auth,
                verify=False,
                timeout=15,
            )
            response.raise_for_status()
            raw = response.json()
        except requests.exceptions.HTTPError as exc:
            raise OpenSearchError(f"OpenSearch mapping error: {exc}") from exc

        for index_data in raw.values():
            mappings = index_data.get("mappings")
            if mappings:
                return mappings
        return {}

    def create_index(self, index: str, mappings: dict | None = None) -> dict:
        """Create an index, optionally with an explicit mappings body."""
        body: dict = {}
        if mappings:
            body["mappings"] = mappings
        try:
            response = requests.put(
                f"{self._base_url}/{index}",
                json=body,
                auth=self._auth,
                verify=False,
                timeout=15,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise OpenSearchError(f"OpenSearch create-index error on {index}: {exc}") from exc
        return response.json()

    def bulk_index(self, index: str, docs: list) -> dict:
        """Bulk-index *docs* (list of dicts) into *index*. Each doc is a full _source body."""
        lines = []
        for doc in docs:
            lines.append('{"index":{}}')
            lines.append(json.dumps(doc, default=str))
        payload = "\n".join(lines) + "\n"
        try:
            response = requests.post(
                f"{self._base_url}/{index}/_bulk",
                data=payload,
                headers={"Content-Type": "application/x-ndjson"},
                auth=self._auth,
                verify=False,
                timeout=15,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise OpenSearchError(f"OpenSearch bulk-index error on {index}: {exc}") from exc
        return response.json()

    def refresh(self, index: str) -> None:
        """Force a refresh so freshly-indexed docs become searchable immediately."""
        try:
            response = requests.post(
                f"{self._base_url}/{index}/_refresh",
                auth=self._auth,
                verify=False,
                timeout=15,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise OpenSearchError(f"OpenSearch refresh error on {index}: {exc}") from exc

    def delete_index(self, index: str) -> None:
        """Delete an index. Used to tear down the Rule Test sandbox index."""
        try:
            response = requests.delete(
                f"{self._base_url}/{index}",
                auth=self._auth,
                verify=False,
                timeout=15,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise OpenSearchError(f"OpenSearch delete-index error on {index}: {exc}") from exc

    def get_field_mapping(self) -> dict:
        """Return {field_path: type} for the alerts index, flattened. TTL-cached."""
        now = time.time()
        if _field_mapping_cache.get("data") is not None and now - _field_mapping_cache.get("ts", 0) < _MAPPING_TTL:
            return _field_mapping_cache["data"]

        try:
            response = requests.get(
                f"{self._base_url}/{_ALERTS_INDEX}/_mapping",
                auth=self._auth,
                verify=False,
                timeout=15,
            )
            response.raise_for_status()
            raw = response.json()
        except requests.exceptions.HTTPError as exc:
            raise OpenSearchError(f"OpenSearch mapping error: {exc}") from exc

        mapping: dict = {}
        for index_data in raw.values():
            props = index_data.get("mappings", {}).get("properties", {})
            _flatten_mapping(props, "", mapping)

        _field_mapping_cache["data"] = mapping
        _field_mapping_cache["ts"] = now
        return mapping

    def get_rule_catalog(self, agent_ids: list | None = None, window_days: int = 7) -> dict:
        """Return rules seen in the data, keyed on rule.id. TTL-cached.

        Returns {rule_id: {description, groups, level, seen_count}}.
        agent_ids restricts the window to specific agents (scope-aware).
        """
        cache_key = ",".join(sorted(str(a) for a in (agent_ids or [])))
        now = time.time()
        entry = _rule_catalog_cache.get(cache_key)
        if entry and now - entry.get("ts", 0) < _RULE_CATALOG_TTL:
            return entry["data"]

        filters: list = [{"range": {"@timestamp": {"gte": f"now-{window_days}d"}}}]
        if agent_ids:
            filters.append({"terms": {"agent.id": [str(a) for a in agent_ids]}})

        body = {
            "size": 0,
            "query": {"bool": {"filter": filters}},
            "aggregations": {
                "by_rule_id": {
                    "terms": {"field": "rule.id", "size": 1000},
                    "aggs": {
                        "desc": {"terms": {"field": "rule.description.keyword", "size": 1}},
                        "groups": {"terms": {"field": "rule.groups", "size": 10}},
                        "level": {"terms": {"field": "rule.level", "size": 1}},
                    },
                }
            },
        }

        try:
            result = self._search(_ALERTS_INDEX, body)
        except OpenSearchError:
            _rule_catalog_cache[cache_key] = {"ts": now, "data": {}}
            return {}

        catalog: dict = {}
        for bucket in result.get("aggregations", {}).get("by_rule_id", {}).get("buckets", []):
            rule_id = str(bucket["key"])
            desc_b = bucket.get("desc", {}).get("buckets", [])
            groups_b = bucket.get("groups", {}).get("buckets", [])
            level_b = bucket.get("level", {}).get("buckets", [])
            catalog[rule_id] = {
                "description": desc_b[0]["key"] if desc_b else "",
                "groups": [b["key"] for b in groups_b],
                "level": level_b[0]["key"] if level_b else 0,
                "seen_count": bucket["doc_count"],
            }

        _rule_catalog_cache[cache_key] = {"ts": now, "data": catalog}
        return catalog

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
            "size": 0,
            "query": {"bool": {"filter": filters}},
            "aggs": {
                "by_cve": {
                    "terms": {"field": "vulnerability.id", "size": 10000},
                    "aggs": {
                        "package": {"terms": {"field": "package.name", "size": 1}},
                        "severity": {"terms": {"field": "vulnerability.severity", "size": 1}},
                        "status": {"terms": {"field": "vulnerability.status", "size": 1}},
                        "version": {"terms": {"field": "package.version", "size": 1}},
                    },
                }
            },
        }
        data = self._search(_VULNS_INDEX, body)
        buckets = data.get("aggregations", {}).get("by_cve", {}).get("buckets", [])

        def _first_key(agg):
            b = agg.get("buckets", [])
            return b[0]["key"] if b else ""

        vulns = [
            {
                "_id": b["key"],
                "vulnerability": {
                    "id": b["key"],
                    "severity": _first_key(b.get("severity", {})),
                    "status": _first_key(b.get("status", {})),
                },
                "package": {
                    "name": _first_key(b.get("package", {})),
                    "version": _first_key(b.get("version", {})),
                },
            }
            for b in buckets
        ]
        total = len(vulns)
        return {
            "vulnerabilities": vulns[offset: offset + limit],
            "total": total,
        }

    def get_vulnerability_by_id(self, agent_id, vuln_id):
        body = {
            "query": {"bool": {"filter": [
                {"term": {"vulnerability.id": vuln_id}},
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

    def get_fleet_events(
        self, agent_ids, minutes=1440, offset=0, limit=100,
        severity=None, search="", agent_id_filter=None,
    ):
        if not agent_ids:
            empty_stats = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0, "events_24h": 0}
            return {"events": [], "total": 0, "stats": empty_stats}

        main_filters = [
            {"terms": {"agent.id": [str(a) for a in agent_ids]}},
            {"range": {"@timestamp": {"gte": f"now-{minutes}m"}}},
        ]
        if agent_id_filter:
            main_filters.append({"term": {"agent.id": str(agent_id_filter)}})
        if severity:
            valid = [s for s in severity if s in _SEVERITY_LEVEL_RANGES]
            if valid:
                should = [{"range": {"rule.level": _SEVERITY_LEVEL_RANGES[s]}} for s in valid]
                main_filters.append({"bool": {"should": should, "minimum_should_match": 1}})
        if search:
            main_filters.append({"match": {"rule.description": search}})

        body = {
            "query": {"bool": {"filter": main_filters}},
            "sort": [{"@timestamp": {"order": "desc"}}],
            "from": offset,
            "size": limit,
            "track_total_hits": True,
            "aggs": {
                "severity_critical": {"filter": {"range": {"rule.level": {"gte": 12}}}},
                "severity_high":     {"filter": {"range": {"rule.level": {"gte": 8, "lt": 12}}}},
                "severity_medium":   {"filter": {"range": {"rule.level": {"gte": 4, "lt": 8}}}},
                "severity_low":      {"filter": {"range": {"rule.level": {"lt": 4}}}},
                "events_24h_global": {
                    "global": {},
                    "aggs": {
                        "within_24h": {
                            "filter": {
                                "bool": {
                                    "filter": [
                                        {"terms": {"agent.id": [str(a) for a in agent_ids]}},
                                        {"range": {"@timestamp": {"gte": "now-1440m"}}},
                                    ]
                                }
                            }
                        }
                    },
                },
            },
        }

        data = self._search(_ALERTS_INDEX, body)
        hits = data["hits"]
        aggs = data.get("aggregations", {})
        total = hits["total"]["value"]

        stats = {
            "critical": aggs.get("severity_critical", {}).get("doc_count", 0),
            "high":     aggs.get("severity_high",     {}).get("doc_count", 0),
            "medium":   aggs.get("severity_medium",   {}).get("doc_count", 0),
            "low":      aggs.get("severity_low",      {}).get("doc_count", 0),
            "total":    total,
            "events_24h": aggs.get("events_24h_global", {}).get("within_24h", {}).get("doc_count", 0),
        }

        return {
            "events": [{"_id": h.get("_id", ""), **h["_source"]} for h in hits["hits"]],
            "total": total,
            "stats": stats,
        }

    def get_route_logs(self, fqdn, log_type, hours=24, offset=0, limit=50, srcip=None):
        filters = [
            {"term": {"data.hostname": fqdn}},
            {"term": {"rule.groups": "bunkerweb"}},
            {"term": {"rule.groups": log_type}},
            {"range": {"timestamp": {"gte": f"now-{hours}h"}}},
        ]
        if srcip:
            filters.append({"term": {"data.srcip": srcip}})
        body = {
            "query": {"bool": {"filter": filters}},
            "sort": [{"timestamp": {"order": "desc"}}],
            "from": offset,
            "size": limit,
            "track_total_hits": True,
            "aggs": {
                "blocked": {"filter": {"term": {"data.status_code": "403"}}},
            },
        }
        data = self._search(_ALERTS_INDEX, body)
        hits = data["hits"]
        total = hits["total"]["value"]
        aggs = data.get("aggregations", {})
        # modsecurity events are all blocks; access log blocks are 403s
        blocked = total if log_type == "modsecurity" else aggs.get("blocked", {}).get("doc_count", 0)
        return {
            "logs": [{"_id": h.get("_id", ""), **h["_source"]} for h in hits["hits"]],
            "total": total,
            "summary": {"total": total, "blocked": blocked},
        }

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

    def get_fields_for_rules(
        self,
        rule_ids: list,
        agent_ids=None,
        window_days: int = 7,
        mapping: dict = None,
        top_values_cap: int = 15,
    ) -> dict:
        """Return populated fields + top values for docs matching rule_ids.

        Returns {field_path: {type, top_values, operators}}.
        Only aggregates on aggregatable (non-text) fields from the mapping.
        """
        from correlations.services.search_compiler import _operators_for_type, _TEXT_TYPES

        mapping = mapping or {}

        # Build candidate field list: core fields + aggregatable mapping fields
        _CORE_FIELD_NAMES = [
            "rule.id", "rule.level", "rule.groups",
            "agent.name", "agent.id",
            "data.srcip", "data.dstip", "data.dstuser",
            "data.audit.comm", "data.sha256",
            "decoder.name",
        ]
        candidate_fields = list(_CORE_FIELD_NAMES)
        # Add aggregatable fields from mapping not already in core list
        for field, ftype in mapping.items():
            if ftype not in _TEXT_TYPES and field not in candidate_fields:
                candidate_fields.append(field)
            if len(candidate_fields) >= 60:
                break

        filters: list = [
            {"range": {"@timestamp": {"gte": f"now-{window_days}d"}}},
            {"terms": {"rule.id": [str(r) for r in rule_ids]}},
        ]
        if agent_ids:
            filters.append({"terms": {"agent.id": [str(a) for a in agent_ids]}})

        aggs = {}
        for field in candidate_fields:
            agg_key = field.replace(".", "_DOT_")
            aggs[agg_key] = {"terms": {"field": field, "size": top_values_cap}}

        body = {
            "size": 0,
            "query": {"bool": {"filter": filters}},
            "aggregations": aggs,
        }

        try:
            result = self._search(_ALERTS_INDEX, body)
        except OpenSearchError:
            return {}

        expanded: dict = {}
        for field in candidate_fields:
            agg_key = field.replace(".", "_DOT_")
            buckets = result.get("aggregations", {}).get(agg_key, {}).get("buckets", [])
            if not buckets:
                continue
            field_type = mapping.get(field, "keyword")
            expanded[field] = {
                "type": field_type,
                "top_values": [b["key"] for b in buckets],
                "operators": _operators_for_type(field_type),
            }

        return expanded

    def get_sample_docs(
        self,
        rule_ids=None,
        agent_ids=None,
        window_days: int = 7,
        limit: int = 10,
    ) -> list:
        """Return a sample of raw Wazuh document _source dicts for grounding."""
        filters: list = [{"range": {"@timestamp": {"gte": f"now-{window_days}d"}}}]
        if rule_ids:
            filters.append({"terms": {"rule.id": [str(r) for r in rule_ids]}})
        if agent_ids:
            filters.append({"terms": {"agent.id": [str(a) for a in agent_ids]}})

        body = {
            "size": limit,
            "query": {"bool": {"filter": filters}},
            "sort": [{"@timestamp": {"order": "desc"}}],
            "_source": [
                "rule.id", "rule.level", "rule.description", "rule.groups",
                "agent.name", "data.srcip", "data.dstip", "data.dstuser",
                "decoder.name",
            ],
        }

        try:
            data = self._search(_ALERTS_INDEX, body)
        except OpenSearchError:
            return []

        return [h.get("_source", {}) for h in data.get("hits", {}).get("hits", [])]
