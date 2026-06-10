"""Rule Test sandbox harness (PRD #439, ADR-0010).

Runs a Scheduled Search Rule against a set of synthetic Sample Documents using the
*real* matcher (the decide path), but against an ephemeral OpenSearch index the testing
flow creates, mapping-clones from the live alerts index, loads, queries, and drops —
with zero production side effects (no Incident/Alert/firing rows).

Key invariants:
  - Index name never matches the `wazuh-alerts-*` glob (uses `vels-ruletest-<uuid>`).
  - The live alerts-index mapping is cloned onto the test index (no dynamic mapping drift).
  - The run is scope-neutralised (`agent_ids=None`).
  - The window is anchored to the latest Sample Document timestamp (time-stable tests).
  - The ephemeral index is always dropped, even on error (`finally`).
"""
import logging
import uuid
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from correlations.models import (
    TEST_STATUS_ERROR,
    TEST_STATUS_FAIL,
    TEST_STATUS_PASS,
)
from correlations.services.search_evaluator import decide

logger = logging.getLogger(__name__)

# A test index must NOT match the wazuh-alerts-* glob, or it becomes visible to every
# consumer of that glob (dashboards, other rules). ADR-0010.
TEST_INDEX_PREFIX = "vels-ruletest-"

# Bound the synthetic payload a single test can push.
MAX_SAMPLES_PER_TEST = 200

_TIMESTAMP_FIELD = "@timestamp"


def build_verdict(expect_fire: bool, decision) -> dict:
    """Pure: turn an Expectation + a Decision into a Test Result (pass/fail + diagnostics)."""
    fired = bool(decision.would_fire)
    passed = fired == bool(expect_fire)
    return {
        "status": TEST_STATUS_PASS if passed else TEST_STATUS_FAIL,
        "passed": passed,
        "expect_fire": bool(expect_fire),
        "fired": fired,
        "diagnostics": decision.diagnostics,
    }


def _anchor_now(samples: list):
    """Anchor 'now' to the latest Sample Document @timestamp so tests are time-stable.

    Falls back to wall-clock when no sample carries a parseable timestamp.
    """
    latest = None
    for doc in samples:
        raw = doc.get(_TIMESTAMP_FIELD) if isinstance(doc, dict) else None
        if not raw:
            continue
        ts = parse_datetime(raw.replace("Z", "+00:00") if isinstance(raw, str) else raw)
        if ts is None:
            continue
        if timezone.is_naive(ts):
            ts = timezone.make_aware(ts, timezone.utc)
        if latest is None or ts > latest:
            latest = ts
    return latest or timezone.now()


def run_rule_test(rule, samples: list, expect_fire: bool) -> dict:
    """Evaluate *rule* against *samples* and return a Test Result dict.

    Never creates an Incident/Alert/SearchFiring/SearchFinding. On any OpenSearch or
    runtime error returns a result with status 'error'. The ephemeral index is always
    dropped.
    """
    from security.opensearch import OpenSearchClient, OpenSearchError

    samples = samples or []
    if len(samples) > MAX_SAMPLES_PER_TEST:
        return {
            "status": TEST_STATUS_ERROR,
            "passed": False,
            "expect_fire": bool(expect_fire),
            "fired": False,
            "diagnostics": None,
            "error": f"Too many sample documents (max {MAX_SAMPLES_PER_TEST}).",
        }

    index = f"{TEST_INDEX_PREFIX}{uuid.uuid4().hex}"
    client = OpenSearchClient()
    created = False
    try:
        mappings = client.get_raw_mapping()
        client.create_index(index, mappings=mappings)
        created = True
        if samples:
            client.bulk_index(index, samples)
        client.refresh(index)

        now = _anchor_now(samples)
        window_start = now - timedelta(minutes=rule.window_minutes)

        # Scope-neutralised (agent_ids=None); decide-only (no materialisation).
        # Honour the rule's time-of-day window (#440), evaluated in the owning org's
        # timezone (UTC for system rules where organization is null).
        from correlations.services.search_compiler import build_time_of_day_filter
        tz_name = rule.organization.timezone if rule.organization_id else "UTC"
        time_filter = build_time_of_day_filter(rule, tz_name)
        decision = decide(rule, None, now, window_start, index=index, client=client, time_filter=time_filter)
        return build_verdict(expect_fire, decision)
    except OpenSearchError as exc:
        # Full detail goes to the server logs; the client only sees a sanitised summary
        # so we never surface raw backend internals (CodeQL py/stack-trace-exposure).
        logger.warning("run_rule_test: OpenSearch error for rule %s: %s", rule.id, exc)
        return {
            "status": TEST_STATUS_ERROR,
            "passed": False,
            "expect_fire": bool(expect_fire),
            "fired": False,
            "diagnostics": None,
            "error": "Search backend error while running the test. Check the server logs for details.",
        }
    except Exception:  # noqa: BLE001 — a test run must never raise to the caller
        # logger.exception captures the full traceback server-side; the client only
        # sees a generic message (CodeQL py/stack-trace-exposure).
        logger.exception("run_rule_test: unexpected error for rule %s", rule.id)
        return {
            "status": TEST_STATUS_ERROR,
            "passed": False,
            "expect_fire": bool(expect_fire),
            "fired": False,
            "diagnostics": None,
            "error": "Unexpected error while running the test. Check the server logs for details.",
        }
    finally:
        if created:
            try:
                client.delete_index(index)
            except OpenSearchError:
                logger.warning("run_rule_test: failed to drop test index %s", index)


def run_rule_test_and_save(test) -> dict:
    """Run a saved SearchRuleTest, persist its last-result summary, and return the result."""
    result = run_rule_test(test.rule, test.samples, test.expect_fire)
    test.last_run_at = timezone.now()
    test.last_status = result["status"]
    test.last_diagnostics = result.get("diagnostics")
    test.save(update_fields=["last_run_at", "last_status", "last_diagnostics", "updated_at"])
    return result
