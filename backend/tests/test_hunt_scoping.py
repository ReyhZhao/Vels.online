"""Scoping-phase tool: propose_hunt_plan (ADR-0018, issue #504).

Exercises the tool's external behaviour directly — it hands a validated structured plan
to its sink and rejects malformed input without recording anything.
"""
import pytest

from hunts.models import Hunt
from hunts.scoping import build_propose_hunt_plan_tool

pytestmark = pytest.mark.django_db


@pytest.fixture
def hunt(db):
    return Hunt.objects.create(title="t", seed_text="q", scope_all_orgs=True, lookback_days=30)


def _capturing_tool(hunt):
    captured = {}
    tool = build_propose_hunt_plan_tool(hunt, record_plan=lambda p: captured.update(p))
    return tool, captured


def test_propose_hunt_plan_records_structured_plan(hunt):
    tool, plan = _capturing_tool(hunt)
    result = tool.executor({
        "refined_question": "Sweep for FIN12 hashes on Windows hosts",
        "hypotheses": ["lateral movement via SMB", "Cobalt Strike beacon"],
        "planned_lenses": ["ioc_search", "top_rules"],
        "suggested_scope": {"all_orgs": False, "org_ids": [1, "2"], "lookback_days": 14},
    })

    assert result.error is None
    assert plan["refined_question"] == "Sweep for FIN12 hashes on Windows hosts"
    assert plan["hypotheses"] == ["lateral movement via SMB", "Cobalt Strike beacon"]
    assert plan["planned_lenses"] == ["ioc_search", "top_rules"]
    assert plan["suggested_scope"] == {"all_orgs": False, "org_ids": [1, 2], "lookback_days": 14}


def test_propose_hunt_plan_defaults_scope_from_hunt(hunt):
    tool, plan = _capturing_tool(hunt)
    tool.executor({"refined_question": "q"})
    # missing suggested_scope falls back to the hunt's current scope/lookback
    assert plan["suggested_scope"]["all_orgs"] is True
    assert plan["suggested_scope"]["lookback_days"] == 30
    assert plan["suggested_scope"]["org_ids"] == []


def test_propose_hunt_plan_rejects_missing_question(hunt):
    tool, plan = _capturing_tool(hunt)
    result = tool.executor({"hypotheses": ["x"]})
    assert result.error is not None
    assert plan == {}
