from unittest.mock import MagicMock, patch

import pytest
import requests

from security.opensearch import OpenSearchClient, OpenSearchError

_BASE_URL = "https://opensearch.test:9200"


@pytest.fixture(autouse=True)
def opensearch_env(monkeypatch):
    monkeypatch.setenv("WAZUH_INDEXER_URL", _BASE_URL)
    monkeypatch.setenv("WAZUH_INDEXER_USER", "admin")
    monkeypatch.setenv("WAZUH_INDEXER_PASSWORD", "secret")


def _search_response(hits, total=None):
    m = MagicMock()
    m.raise_for_status.return_value = None
    actual_total = total if total is not None else len(hits)
    m.json.return_value = {
        "hits": {
            "hits": [{"_source": h} for h in hits],
            "total": {"value": actual_total},
        }
    }
    return m


def _agg_response(buckets):
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = {
        "hits": {"hits": [], "total": {"value": 0}},
        "aggregations": {"by_severity": {"buckets": buckets}},
    }
    return m


# ------------------------------------------ get_agent_events


@patch("security.opensearch.requests.post")
def test_get_agent_events_queries_alerts_index(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_events("001")
    url = mock_post.call_args[0][0]
    assert "wazuh-alerts-4.x-" in url
    assert "_search" in url


@patch("security.opensearch.requests.post")
def test_get_agent_events_returns_events_and_total(mock_post):
    events = [
        {"@timestamp": "2024-01-15T10:00:00Z", "rule": {"description": "SSH brute force", "level": 10, "id": "5710"}, "agent": {"id": "001", "name": "server-01"}},
    ]
    mock_post.return_value = _search_response(events, total=5)
    result = OpenSearchClient().get_agent_events("001")
    assert result["events"] == events
    assert result["total"] == 5


@patch("security.opensearch.requests.post")
def test_get_agent_events_filters_by_agent_id(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_events("042")
    body = mock_post.call_args[1]["json"]
    filters = body["query"]["bool"]["filter"]
    agent_filter = next(f for f in filters if "term" in f)
    assert agent_filter["term"]["agent.id"] == "042"


@patch("security.opensearch.requests.post")
def test_get_agent_events_respects_offset_and_limit(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_events("001", offset=50, limit=25)
    body = mock_post.call_args[1]["json"]
    assert body["from"] == 50
    assert body["size"] == 25


@patch("security.opensearch.requests.post")
def test_get_agent_events_severity_filter_adds_level_range(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_events("001", severity=["critical"])
    body = mock_post.call_args[1]["json"]
    filters = body["query"]["bool"]["filter"]
    severity_filter = next(f for f in filters if "bool" in f)
    should = severity_filter["bool"]["should"]
    assert should == [{"range": {"rule.level": {"gte": 12}}}]


@patch("security.opensearch.requests.post")
def test_get_agent_events_multiple_severities_build_should_clauses(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_events("001", severity=["high", "low"])
    body = mock_post.call_args[1]["json"]
    filters = body["query"]["bool"]["filter"]
    severity_filter = next(f for f in filters if "bool" in f)
    should = severity_filter["bool"]["should"]
    assert {"range": {"rule.level": {"gte": 8, "lt": 12}}} in should
    assert {"range": {"rule.level": {"lt": 4}}} in should
    assert severity_filter["bool"]["minimum_should_match"] == 1


@patch("security.opensearch.requests.post")
def test_get_agent_events_no_severity_omits_level_filter(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_events("001", severity=None)
    body = mock_post.call_args[1]["json"]
    filters = body["query"]["bool"]["filter"]
    assert not any("bool" in f for f in filters)


@patch("security.opensearch.requests.post")
def test_get_agent_events_search_adds_match_query(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_events("001", search="brute force")
    body = mock_post.call_args[1]["json"]
    filters = body["query"]["bool"]["filter"]
    match_filter = next(f for f in filters if "match" in f)
    assert match_filter["match"]["rule.description"] == "brute force"


@patch("security.opensearch.requests.post")
def test_get_agent_events_empty_search_omits_match_query(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_events("001", search="")
    body = mock_post.call_args[1]["json"]
    filters = body["query"]["bool"]["filter"]
    assert not any("match" in f for f in filters)


@patch("security.opensearch.requests.post")
def test_get_agent_events_hours_controls_time_range(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_events("001", hours=6)
    body = mock_post.call_args[1]["json"]
    filters = body["query"]["bool"]["filter"]
    range_filter = next(f for f in filters if "range" in f)
    assert range_filter["range"]["@timestamp"]["gte"] == "now-6h"


# ------------------------------------------ get_agent_vulnerabilities


@patch("security.opensearch.requests.post")
def test_get_agent_vulnerabilities_queries_vulns_index(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_vulnerabilities("001")
    url = mock_post.call_args[0][0]
    assert "wazuh-states-vulnerabilities" in url


@patch("security.opensearch.requests.post")
def test_get_agent_vulnerabilities_returns_vulns_and_total(mock_post):
    vulns = [
        {"vulnerability": {"id": "CVE-2024-0001", "severity": "High", "status": "Fixed"}, "package": {"name": "openssl", "version": "1.1.1"}},
    ]
    mock_post.return_value = _search_response(vulns, total=10)
    result = OpenSearchClient().get_agent_vulnerabilities("001")
    assert result["vulnerabilities"] == vulns
    assert result["total"] == 10


@patch("security.opensearch.requests.post")
def test_get_agent_vulnerabilities_respects_offset_and_limit(mock_post):
    mock_post.return_value = _search_response([])
    OpenSearchClient().get_agent_vulnerabilities("001", offset=20, limit=10)
    body = mock_post.call_args[1]["json"]
    assert body["from"] == 20
    assert body["size"] == 10


# ------------------------------------------ get_vulnerabilities_summary


@patch("security.opensearch.requests.post")
def test_get_vulnerabilities_summary_aggregates_by_severity(mock_post):
    mock_post.return_value = _agg_response([
        {"key": "Critical", "doc_count": 3},
        {"key": "High", "doc_count": 5},
        {"key": "Medium", "doc_count": 10},
        {"key": "Low", "doc_count": 2},
    ])
    agents = [{"id": "001", "status": "active"}]
    result = OpenSearchClient().get_vulnerabilities_summary(agents)
    assert result == {"critical": 3, "high": 5, "medium": 10, "low": 2}


@patch("security.opensearch.requests.post")
def test_get_vulnerabilities_summary_skips_inactive_agents(mock_post):
    agents = [{"id": "001", "status": "disconnected"}]
    result = OpenSearchClient().get_vulnerabilities_summary(agents)
    assert result == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    mock_post.assert_not_called()


@patch("security.opensearch.requests.post")
def test_get_vulnerabilities_summary_empty_agent_list(mock_post):
    result = OpenSearchClient().get_vulnerabilities_summary([])
    assert result == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    mock_post.assert_not_called()


# ------------------------------------------ get_events_count


@patch("security.opensearch.requests.post")
def test_get_events_count_returns_total(mock_post):
    mock_post.return_value = _search_response([], total=42)
    agents = [{"id": "001", "status": "active"}, {"id": "002", "status": "active"}]
    result = OpenSearchClient().get_events_count(agents)
    assert result == 42


@patch("security.opensearch.requests.post")
def test_get_events_count_skips_inactive_agents(mock_post):
    agents = [{"id": "001", "status": "disconnected"}]
    result = OpenSearchClient().get_events_count(agents)
    assert result == 0
    mock_post.assert_not_called()


@patch("security.opensearch.requests.post")
def test_get_events_count_empty_agent_list(mock_post):
    result = OpenSearchClient().get_events_count([])
    assert result == 0
    mock_post.assert_not_called()


# ------------------------------------------ error handling


@patch("security.opensearch.requests.post")
def test_http_error_raises_opensearch_error(mock_post):
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    mock_post.return_value = resp
    with pytest.raises(OpenSearchError, match="500"):
        OpenSearchClient().get_agent_events("001")
