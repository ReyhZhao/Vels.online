import pytest

from security.scoring import score_vulnerabilities


def test_empty_input():
    assert score_vulnerabilities([]) == []


def test_single_item():
    result = score_vulnerabilities([{"cve_id": "CVE-2024-0001", "severity": "high", "agent_count": 3}])
    assert len(result) == 1
    assert result[0]["cve_id"] == "CVE-2024-0001"
    assert result[0]["affected_agent_count"] == 3
    assert result[0]["impact_score"] == 21  # 7 × 3


def test_correct_impact_score_values():
    records = [
        {"cve_id": "CVE-A", "severity": "critical", "agent_count": 2},
        {"cve_id": "CVE-B", "severity": "high", "agent_count": 5},
        {"cve_id": "CVE-C", "severity": "medium", "agent_count": 10},
        {"cve_id": "CVE-D", "severity": "low", "agent_count": 100},
    ]
    result = score_vulnerabilities(records)
    by_id = {r["cve_id"]: r for r in result}
    assert by_id["CVE-A"]["impact_score"] == 20   # 10 × 2
    assert by_id["CVE-B"]["impact_score"] == 35   # 7 × 5
    assert by_id["CVE-C"]["impact_score"] == 40   # 4 × 10
    assert by_id["CVE-D"]["impact_score"] == 100  # 1 × 100


def test_ranking_higher_score_first():
    records = [
        {"cve_id": "CVE-LOW", "severity": "low", "agent_count": 1},
        {"cve_id": "CVE-CRIT", "severity": "critical", "agent_count": 5},
        {"cve_id": "CVE-HIGH", "severity": "high", "agent_count": 3},
    ]
    result = score_vulnerabilities(records)
    assert result[0]["cve_id"] == "CVE-CRIT"   # 50
    assert result[1]["cve_id"] == "CVE-HIGH"   # 21
    assert result[2]["cve_id"] == "CVE-LOW"    # 1


def test_all_same_severity_ranked_by_agent_count():
    records = [
        {"cve_id": "CVE-2024-0003", "severity": "medium", "agent_count": 2},
        {"cve_id": "CVE-2024-0001", "severity": "medium", "agent_count": 8},
        {"cve_id": "CVE-2024-0002", "severity": "medium", "agent_count": 5},
    ]
    result = score_vulnerabilities(records)
    assert result[0]["cve_id"] == "CVE-2024-0001"
    assert result[1]["cve_id"] == "CVE-2024-0002"
    assert result[2]["cve_id"] == "CVE-2024-0003"


def test_deduplication_sums_agent_counts():
    records = [
        {"cve_id": "CVE-2024-0001", "severity": "high", "agent_count": 3},
        {"cve_id": "CVE-2024-0001", "severity": "high", "agent_count": 4},
        {"cve_id": "CVE-2024-0002", "severity": "high", "agent_count": 6},
    ]
    result = score_vulnerabilities(records)
    assert len(result) == 2
    by_id = {r["cve_id"]: r for r in result}
    assert by_id["CVE-2024-0001"]["affected_agent_count"] == 7
    assert by_id["CVE-2024-0001"]["impact_score"] == 49  # 7 × 7


def test_deduplication_preserves_ranking():
    records = [
        {"cve_id": "CVE-A", "severity": "high", "agent_count": 2},
        {"cve_id": "CVE-B", "severity": "critical", "agent_count": 1},
        {"cve_id": "CVE-A", "severity": "high", "agent_count": 2},  # merged → 4 agents → 28
    ]
    result = score_vulnerabilities(records)
    # CVE-B: 10×1=10, CVE-A: 7×4=28 → CVE-A should rank first
    assert result[0]["cve_id"] == "CVE-A"
    assert result[1]["cve_id"] == "CVE-B"


def test_tie_breaking_is_alphabetical_by_cve_id():
    records = [
        {"cve_id": "CVE-2024-0003", "severity": "high", "agent_count": 2},
        {"cve_id": "CVE-2024-0001", "severity": "high", "agent_count": 2},
        {"cve_id": "CVE-2024-0002", "severity": "high", "agent_count": 2},
    ]
    result = score_vulnerabilities(records)
    assert [r["cve_id"] for r in result] == ["CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0003"]


def test_mixed_severity_and_agent_count():
    records = [
        {"cve_id": "CVE-A", "severity": "critical", "agent_count": 1},  # 10
        {"cve_id": "CVE-B", "severity": "high", "agent_count": 2},      # 14
        {"cve_id": "CVE-C", "severity": "medium", "agent_count": 4},    # 16
        {"cve_id": "CVE-D", "severity": "low", "agent_count": 20},      # 20
    ]
    result = score_vulnerabilities(records)
    assert [r["cve_id"] for r in result] == ["CVE-D", "CVE-C", "CVE-B", "CVE-A"]
