"""
Tests for the AI incident triage pipeline.

Covers:
  - incidents/llm/ provider parsing (unit)
  - run_incident_triage Celery task (integration, mocked provider)
  - post-save signal (unit, mocked task)
  - IncidentTriageView API endpoint (integration)
"""
import pytest
from unittest.mock import MagicMock, patch

from security.models import Organization, OrganizationMembership
from incidents.models import Comment, Incident
from incidents.llm.base import TriageConfigError, TriageError, TriageResult
from incidents.llm.gemini import _parse_result


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(
        username="staff", password="pass", is_staff=True
    )


@pytest.fixture
def member_user(db, django_user_model):
    return django_user_model.objects.create_user(username="member", password="pass")


@pytest.fixture
def member(member_user, acme):
    OrganizationMembership.objects.create(user=member_user, organization=acme)
    return member_user


def make_incident(acme, state="new", severity="medium", n=None, source_kind="wazuh_event"):
    count = Incident.objects.count() if n is None else n
    return Incident.objects.create(
        organization=acme,
        title="Suspicious login from unknown IP",
        description="Multiple failed SSH attempts",
        display_id=f"INC-2026-{count + 1:04d}",
        source_kind=source_kind,
        source_ref={"rule_id": 5712, "level": 8, "agent_name": "web-01"},
        state=state,
        severity=severity,
    )


# ── LLM provider parsing ─────────────────────────────────────────────────────


def test_parse_result_valid():
    data = {
        "severity_recommendation": "high",
        "summary": "SSH brute force attempt.",
        "primary_action": "assign_to_analyst",
        "secondary_action": "monitor",
        "false_positive_confidence": 0.1,
    }
    result = _parse_result(data, provider="gemini")
    assert result.severity_recommendation == "high"
    assert result.primary_action == "assign_to_analyst"
    assert result.secondary_action == "monitor"
    assert result.false_positive_confidence == 0.1
    assert result.provider == "gemini"


def test_parse_result_invalid_severity_defaults_to_medium():
    data = {
        "severity_recommendation": "severe",
        "summary": "Something.",
        "primary_action": "monitor",
        "false_positive_confidence": 0.0,
    }
    result = _parse_result(data, provider="gemini")
    assert result.severity_recommendation == "medium"


def test_parse_result_invalid_action_defaults_to_assign():
    data = {
        "severity_recommendation": "low",
        "summary": ".",
        "primary_action": "do_something_weird",
        "false_positive_confidence": 0.0,
    }
    result = _parse_result(data, provider="gemini")
    assert result.primary_action == "assign_to_analyst"


def test_parse_result_invalid_secondary_action_cleared():
    data = {
        "severity_recommendation": "low",
        "summary": ".",
        "primary_action": "monitor",
        "secondary_action": "invalid_action",
        "false_positive_confidence": 0.0,
    }
    result = _parse_result(data, provider="gemini")
    assert result.secondary_action is None


def test_parse_result_confidence_clamped():
    data = {
        "severity_recommendation": "low",
        "summary": ".",
        "primary_action": "monitor",
        "false_positive_confidence": 1.5,
    }
    result = _parse_result(data, provider="gemini")
    assert result.false_positive_confidence == 1.0


def test_parse_result_disposition_confidence_valid():
    data = {
        "severity_recommendation": "high",
        "summary": "Real phishing.",
        "primary_action": "assign_to_analyst",
        "false_positive_confidence": 0.05,
        "disposition_confidence": 0.9,
    }
    result = _parse_result(data, provider="gemini")
    assert result.disposition_confidence == 0.9


def test_parse_result_disposition_confidence_defaults_to_zero_when_missing():
    data = {
        "severity_recommendation": "high",
        "summary": ".",
        "primary_action": "assign_to_analyst",
        "false_positive_confidence": 0.05,
    }
    result = _parse_result(data, provider="gemini")
    assert result.disposition_confidence == 0.0


def test_parse_result_disposition_confidence_clamped_and_coerced():
    assert _parse_result(
        {"primary_action": "monitor", "disposition_confidence": 1.5}, provider="gemini"
    ).disposition_confidence == 1.0
    assert _parse_result(
        {"primary_action": "monitor", "disposition_confidence": "not-a-number"}, provider="gemini"
    ).disposition_confidence == 0.0


# ── run_incident_triage task ──────────────────────────────────────────────────


def _make_triage_result(**kwargs):
    defaults = dict(
        severity_recommendation="medium",
        summary="Normal activity.",
        primary_action="assign_to_analyst",
        secondary_action=None,
        false_positive_confidence=0.1,
        disposition_confidence=0.5,
        provider="gemini",
    )
    defaults.update(kwargs)
    return TriageResult(**defaults)


def _run_task(incident_id, provider_result=None, provider_error=None):
    """Run run_incident_triage synchronously via apply(), with a mocked provider."""
    from incidents.tasks import run_incident_triage

    mock_provider = MagicMock()
    if provider_error:
        mock_provider.triage_incident.side_effect = provider_error
    else:
        mock_provider.triage_incident.return_value = provider_result

    with patch("incidents.tasks.get_triage_provider", return_value=mock_provider):
        run_incident_triage.apply(args=(incident_id,))


@pytest.mark.django_db
def test_triage_task_creates_ai_comment(acme):
    incident = make_incident(acme)
    result = _make_triage_result(summary="Test summary.", false_positive_confidence=0.1)
    _run_task(incident.id, provider_result=result)

    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.body == "Test summary."
    assert comment.author is None
    assert comment.metadata["primary_action"] == "assign_to_analyst"
    assert comment.metadata["auto_closed"] is False
    assert comment.metadata["disposition_confidence"] == 0.5


@pytest.mark.django_db
def test_triage_task_auto_closes_on_high_fp_confidence(acme):
    acme.triage_fp_threshold = 0.95
    acme.save()
    incident = make_incident(acme)
    result = _make_triage_result(
        primary_action="close_as_false_positive",
        false_positive_confidence=0.97,
    )
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.state == Incident.STATE_CLOSED
    assert incident.closure_reason == Incident.CLOSURE_FALSE_POSITIVE
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["auto_closed"] is True


@pytest.mark.django_db
def test_triage_task_does_not_auto_close_below_threshold(acme):
    acme.triage_fp_threshold = 0.95
    acme.save()
    incident = make_incident(acme)
    result = _make_triage_result(false_positive_confidence=0.80)
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    # Triage always advances to triaged; auto_close is False because confidence < threshold
    assert incident.state == Incident.STATE_TRIAGED
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["auto_closed"] is False


@pytest.mark.django_db
def test_partner_incident_is_exempt_from_fp_auto_close(acme):
    """A partner incident with FP-confidence above threshold stays open (#674, ADR-0032)."""
    acme.triage_fp_threshold = 0.95
    acme.save()
    incident = make_incident(acme, source_kind=Incident.SOURCE_PARTNER)
    result = _make_triage_result(
        primary_action="close_as_false_positive",
        false_positive_confidence=0.99,
    )
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.state != Incident.STATE_CLOSED
    assert incident.closure_reason != Incident.CLOSURE_FALSE_POSITIVE
    # Classify still runs and records its recommendation
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["auto_closed"] is False
    assert comment.metadata["false_positive_confidence"] == 0.99


@pytest.mark.django_db
def test_non_partner_incident_still_auto_closes_at_same_confidence(acme):
    """The equivalent non-partner incident with the same FP-confidence still auto-closes."""
    acme.triage_fp_threshold = 0.95
    acme.save()
    incident = make_incident(acme, source_kind="wazuh_event")
    result = _make_triage_result(
        primary_action="close_as_false_positive",
        false_positive_confidence=0.99,
    )
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.state == Incident.STATE_CLOSED
    assert incident.closure_reason == Incident.CLOSURE_FALSE_POSITIVE


# ── recommendation-gated false-positive close (#699, ADR-0024) ────────────────


@pytest.mark.django_db
def test_recommendation_gated_close_between_bars(acme):
    """Model recommends close, FP confidence between close_bar and threshold → auto-closes."""
    acme.triage_fp_threshold = 0.95
    acme.triage_fp_close_bar = 0.80
    acme.save()
    incident = make_incident(acme)
    result = _make_triage_result(
        primary_action="close_as_false_positive",
        false_positive_confidence=0.87,
    )
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.state == Incident.STATE_CLOSED
    assert incident.closure_reason == Incident.CLOSURE_FALSE_POSITIVE
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["auto_closed"] is True
    assert comment.metadata["auto_close_reason"] == "recommendation"


@pytest.mark.django_db
def test_threshold_close_records_threshold_reason(acme):
    """High FP confidence alone auto-closes and is recorded as the threshold path."""
    acme.triage_fp_threshold = 0.95
    acme.triage_fp_close_bar = 0.80
    acme.save()
    incident = make_incident(acme)
    result = _make_triage_result(
        primary_action="monitor",
        false_positive_confidence=0.97,
    )
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.state == Incident.STATE_CLOSED
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["auto_close_reason"] == "threshold"


@pytest.mark.django_db
def test_no_close_when_recommendation_absent_below_threshold(acme):
    """FP clears close_bar but the model did not recommend closing → stays open."""
    acme.triage_fp_threshold = 0.95
    acme.triage_fp_close_bar = 0.80
    acme.save()
    incident = make_incident(acme)
    result = _make_triage_result(
        primary_action="assign_to_analyst",
        false_positive_confidence=0.87,
    )
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.state == Incident.STATE_TRIAGED
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["auto_closed"] is False
    assert comment.metadata["auto_close_reason"] is None


@pytest.mark.django_db
def test_no_close_when_recommendation_below_close_bar(acme):
    """Model recommends closing but FP is below the close_bar floor → stays open."""
    acme.triage_fp_threshold = 0.95
    acme.triage_fp_close_bar = 0.80
    acme.save()
    incident = make_incident(acme)
    result = _make_triage_result(
        primary_action="close_as_false_positive",
        false_positive_confidence=0.70,
    )
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.state == Incident.STATE_TRIAGED
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["auto_closed"] is False
    assert comment.metadata["auto_close_reason"] is None


@pytest.mark.django_db
def test_partner_exempt_from_recommendation_gated_close(acme):
    """A partner incident is not auto-closed even via the recommendation-gated path."""
    acme.triage_fp_threshold = 0.95
    acme.triage_fp_close_bar = 0.80
    acme.save()
    incident = make_incident(acme, source_kind=Incident.SOURCE_PARTNER)
    result = _make_triage_result(
        primary_action="close_as_false_positive",
        false_positive_confidence=0.87,
    )
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.state != Incident.STATE_CLOSED
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["auto_closed"] is False
    assert comment.metadata["auto_close_reason"] is None


@pytest.mark.django_db
def test_triage_task_escalates_severity_within_cap(acme):
    # low (1) → critical (4) is 3 levels; capped to 2 → result is high (3)
    incident = make_incident(acme, severity="low")
    result = _make_triage_result(severity_recommendation="critical", false_positive_confidence=0.0)
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.severity == "high"


@pytest.mark.django_db
def test_triage_task_escalates_severity_within_2_levels(acme):
    # medium (2) → critical (4) is exactly 2 levels; applied directly
    incident = make_incident(acme, severity="medium")
    result = _make_triage_result(severity_recommendation="critical", false_positive_confidence=0.0)
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.severity == "critical"


@pytest.mark.django_db
def test_triage_task_downgrades_severity_within_cap(acme):
    # critical (4) → low (1) is 3 levels; capped to 2 → result is medium (2)
    incident = make_incident(acme, severity="critical")
    result = _make_triage_result(severity_recommendation="low", false_positive_confidence=0.0)
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.severity == "medium"


@pytest.mark.django_db
def test_triage_task_downgrades_severity_within_2_levels(acme):
    # critical (4) → medium (2) is exactly 2 levels; applied directly
    incident = make_incident(acme, severity="critical")
    result = _make_triage_result(severity_recommendation="medium", false_positive_confidence=0.0)
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.severity == "medium"


@pytest.mark.django_db
def test_triage_task_no_severity_change_when_same(acme):
    incident = make_incident(acme, severity="medium")
    result = _make_triage_result(severity_recommendation="medium", false_positive_confidence=0.0)
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.severity == "medium"


@pytest.mark.django_db
def test_triage_task_posts_system_comment_on_max_retries_exceeded(acme):
    incident = make_incident(acme)
    # Exhaust all retries by making the provider always fail
    _run_task(incident.id, provider_error=TriageError("API down"))

    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_SYSTEM)
    assert "API down" in comment.body or "could not be completed" in comment.body


@pytest.mark.django_db
def test_triage_task_posts_system_comment_immediately_on_config_error(acme):
    incident = make_incident(acme)
    _run_task(incident.id, provider_error=TriageConfigError("GEMINI_API_KEY is not configured"))

    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_SYSTEM)
    assert "misconfigured" in comment.body
    assert "GEMINI_API_KEY" in comment.body


@pytest.mark.django_db
def test_triage_task_does_not_retry_on_config_error(acme):
    incident = make_incident(acme)
    from incidents.tasks import run_incident_triage

    mock_provider = MagicMock()
    mock_provider.triage_incident.side_effect = TriageConfigError("No key")
    with patch("incidents.tasks.get_triage_provider", return_value=mock_provider):
        run_incident_triage.apply(args=(incident.id,))

    assert mock_provider.triage_incident.call_count == 1


@pytest.mark.django_db
def test_factory_raises_config_error_for_wrong_provider_class(acme):
    from incidents.llm.factory import get_triage_provider
    from django.test import override_settings
    with override_settings(TRIAGE_LLM_PROVIDER="exceptions.llm.ollama.OllamaProvider"):
        with pytest.raises(TriageConfigError, match="BaseTriageProvider"):
            get_triage_provider()


@pytest.mark.django_db
def test_factory_raises_config_error_for_bad_module_path(acme):
    from incidents.llm.factory import get_triage_provider
    from django.test import override_settings
    with override_settings(TRIAGE_LLM_PROVIDER="nonexistent.module.SomeProvider"):
        with pytest.raises(TriageConfigError, match="cannot be imported"):
            get_triage_provider()


@pytest.mark.django_db
def test_factory_raises_config_error_for_bad_class_name(acme):
    from incidents.llm.factory import get_triage_provider
    from django.test import override_settings
    with override_settings(TRIAGE_LLM_PROVIDER="incidents.llm.ollama.NonExistentProvider"):
        with pytest.raises(TriageConfigError, match="not found in module"):
            get_triage_provider()


@pytest.mark.django_db
def test_triage_task_does_not_retry_when_factory_raises_config_error(acme):
    incident = make_incident(acme)
    from incidents.tasks import run_incident_triage

    with patch("incidents.tasks.get_triage_provider", side_effect=TriageConfigError("wrong module")):
        run_incident_triage.apply(args=(incident.id,))

    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_SYSTEM)
    assert "misconfigured" in comment.body
    assert "wrong module" in comment.body


@pytest.mark.django_db
def test_triage_task_missing_incident_exits_cleanly():
    from incidents.tasks import run_incident_triage
    with patch("incidents.tasks.get_triage_provider") as mock_factory:
        run_incident_triage.apply(args=(99999,))
    mock_factory.return_value.triage_incident.assert_not_called()


# ── prompt context ───────────────────────────────────────────────────────────


def test_build_system_prompt_no_context():
    from incidents.llm.gemini import SYSTEM_PROMPT, _build_system_prompt
    assert _build_system_prompt("") == SYSTEM_PROMPT
    assert _build_system_prompt() == SYSTEM_PROMPT


def test_build_system_prompt_appends_org_context():
    from incidents.llm.gemini import SYSTEM_PROMPT, _build_system_prompt
    result = _build_system_prompt("", "treat SSH from 10.0.0.1 as low priority")
    assert result.startswith(SYSTEM_PROMPT)
    assert "--- Organisation context ---" in result
    assert "treat SSH from 10.0.0.1 as low priority" in result


def test_build_system_prompt_source_kind_inbound_email():
    from incidents.llm.gemini import SYSTEM_PROMPT, _build_system_prompt
    result = _build_system_prompt("inbound_email", "")
    assert result.startswith(SYSTEM_PROMPT)
    assert "--- Source context ---" in result
    assert "security team mailbox" in result
    assert "--- Organisation context ---" not in result


def test_build_system_prompt_source_kind_wazuh_event():
    from incidents.llm.gemini import _build_system_prompt
    result = _build_system_prompt("wazuh_event")
    assert "Wazuh SIEM" in result
    assert "--- Source context ---" in result


def test_build_system_prompt_unknown_source_kind_has_no_preamble():
    from incidents.llm.gemini import SYSTEM_PROMPT, _build_system_prompt
    result = _build_system_prompt("api")
    assert result == SYSTEM_PROMPT


def test_build_system_prompt_all_sections():
    from incidents.llm.gemini import SYSTEM_PROMPT, _build_system_prompt
    result = _build_system_prompt("wazuh_event", "Escalate all high-severity alerts.")
    assert result.startswith(SYSTEM_PROMPT)
    assert "--- Source context ---" in result
    assert "--- Organisation context ---" in result
    assert "Escalate all high-severity alerts." in result


@pytest.mark.django_db
def test_triage_task_passes_prompt_context_to_provider(acme):
    acme.triage_prompt_context = "Healthcare org — escalate PHI alerts."
    acme.save()
    incident = make_incident(acme)
    result = _make_triage_result()

    from incidents.tasks import run_incident_triage
    mock_provider = MagicMock()
    mock_provider.triage_incident.return_value = result

    with patch("incidents.tasks.get_triage_provider", return_value=mock_provider):
        run_incident_triage.apply(args=(incident.id,))

    _, kwargs = mock_provider.triage_incident.call_args
    assert kwargs.get("extra_context") == "Healthcare org — escalate PHI alerts."


@pytest.mark.django_db
def test_triage_task_passes_empty_context_when_unset(acme):
    incident = make_incident(acme)
    result = _make_triage_result()

    from incidents.tasks import run_incident_triage
    mock_provider = MagicMock()
    mock_provider.triage_incident.return_value = result

    with patch("incidents.tasks.get_triage_provider", return_value=mock_provider):
        run_incident_triage.apply(args=(incident.id,))

    _, kwargs = mock_provider.triage_incident.call_args
    assert kwargs.get("extra_context") == ""


# ── post-save signal ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_signal_enqueues_triage_on_new_incident(acme):
    with patch("incidents.signals.acquire_triage_lock", return_value=True) as mock_lock:
        with patch("incidents.signals.enrich_iocs_then_triage") as mock_task:
            with patch("incidents.signals.transaction.on_commit", side_effect=lambda f: f()):
                mock_task.delay = MagicMock()
                incident = make_incident(acme, state="new")
                mock_lock.assert_called_once_with(incident.id)
                mock_task.delay.assert_called_once_with(incident.id)


@pytest.mark.django_db
def test_signal_does_not_enqueue_for_non_new_state(acme):
    with patch("incidents.signals.acquire_triage_lock", return_value=True):
        with patch("incidents.signals.enrich_iocs_then_triage") as mock_task:
            with patch("incidents.signals.transaction.on_commit", side_effect=lambda f: f()):
                mock_task.delay = MagicMock()
                make_incident(acme, state="triaged")
                mock_task.delay.assert_not_called()


@pytest.mark.django_db
def test_signal_does_not_enqueue_when_lock_taken(acme):
    with patch("incidents.signals.acquire_triage_lock", return_value=False):
        with patch("incidents.signals.enrich_iocs_then_triage") as mock_task:
            with patch("incidents.signals.transaction.on_commit", side_effect=lambda f: f()):
                mock_task.delay = MagicMock()
                make_incident(acme, state="new")
                mock_task.delay.assert_not_called()


# ── IncidentTriageView API ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_triage_endpoint_requires_auth(client, acme):
    incident = make_incident(acme)
    response = client.post(f"/api/incidents/{incident.display_id}/triage/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_triage_endpoint_requires_staff(client, member, acme):
    incident = make_incident(acme)
    client.force_login(member)
    response = client.post(f"/api/incidents/{incident.display_id}/triage/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_triage_endpoint_returns_202_for_staff(client, staff_user, acme):
    incident = make_incident(acme)
    client.force_login(staff_user)
    with patch("incidents.views.acquire_triage_lock", return_value=True):
        with patch("incidents.views.run_incident_triage") as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(f"/api/incidents/{incident.display_id}/triage/")
    assert response.status_code == 202
    mock_task.delay.assert_called_once_with(incident.id)


@pytest.mark.django_db
def test_triage_endpoint_returns_409_when_lock_taken(client, staff_user, acme):
    incident = make_incident(acme)
    client.force_login(staff_user)
    with patch("incidents.views.acquire_triage_lock", return_value=False):
        response = client.post(f"/api/incidents/{incident.display_id}/triage/")
    assert response.status_code == 409


@pytest.mark.django_db
def test_triage_endpoint_returns_404_for_unknown_incident(client, staff_user):
    client.force_login(staff_user)
    response = client.post("/api/incidents/INC-9999-9999/triage/")
    assert response.status_code == 404


# ── related incident correlation ─────────────────────────────────────────────


def _run_task_with_correlation(incident_id, triage_result, correlation_result=None):
    """Run triage task with mocked provider supporting correlation."""
    from incidents.models import Incident as _Incident
    from incidents.llm.base import CorrelationResult
    from incidents.tasks import run_incident_triage

    if correlation_result is None:
        correlation_result = CorrelationResult()

    mock_provider = MagicMock()
    mock_provider.triage_incident.return_value = triage_result
    mock_provider.find_related_incidents.return_value = correlation_result

    with patch("incidents.tasks.get_triage_provider", return_value=mock_provider):
        run_incident_triage.apply(args=(incident_id,))

    return mock_provider


@pytest.mark.django_db
def test_correlation_not_called_when_no_candidates(acme):
    incident = make_incident(acme)
    result = _make_triage_result()
    mock_provider = _run_task_with_correlation(incident.id, result)
    mock_provider.find_related_incidents.assert_not_called()


@pytest.mark.django_db
def test_correlation_triggers_retriage_when_high_confidence(acme):
    from incidents.llm.base import CorrelationResult

    older = make_incident(acme, n=0)
    incident = make_incident(acme, n=1)

    correlation = CorrelationResult(
        related_incident_ids=[older.id],
        correlation_summary="Same source IP seen in both incidents.",
        max_confidence=0.85,
    )
    first_result = _make_triage_result(summary="Initial triage.")
    second_result = _make_triage_result(summary="Re-triage with correlation context.")
    mock_provider = MagicMock()
    mock_provider.triage_incident.side_effect = [first_result, second_result]
    mock_provider.find_related_incidents.return_value = correlation

    from incidents.tasks import run_incident_triage
    with patch("incidents.tasks.get_triage_provider", return_value=mock_provider):
        run_incident_triage.apply(args=(incident.id,))

    assert mock_provider.triage_incident.call_count == 2
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.body == "Re-triage with correlation context."
    assert older.id in comment.metadata["related_incident_ids"]
    assert comment.metadata["correlation_summary"] == "Same source IP seen in both incidents."


@pytest.mark.django_db
def test_correlation_skipped_when_confidence_below_threshold(acme):
    from incidents.llm.base import CorrelationResult

    older = make_incident(acme, n=0)
    incident = make_incident(acme, n=1)

    correlation = CorrelationResult(
        related_incident_ids=[older.id],
        correlation_summary="Possible link.",
        max_confidence=0.5,
    )
    result = _make_triage_result(summary="No re-triage expected.")
    mock_provider = MagicMock()
    mock_provider.triage_incident.return_value = result
    mock_provider.find_related_incidents.return_value = correlation

    from incidents.tasks import run_incident_triage
    with patch("incidents.tasks.get_triage_provider", return_value=mock_provider):
        run_incident_triage.apply(args=(incident.id,))

    assert mock_provider.triage_incident.call_count == 1
    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.metadata["related_incident_ids"] == []


@pytest.mark.django_db
def test_correlation_failure_does_not_block_triage(acme):
    incident = make_incident(acme)
    result = _make_triage_result(summary="Triage completed despite correlation error.")
    mock_provider = MagicMock()
    mock_provider.triage_incident.return_value = result
    mock_provider.find_related_incidents.side_effect = Exception("LLM error")

    from incidents.tasks import run_incident_triage
    with patch("incidents.tasks.get_triage_provider", return_value=mock_provider):
        # Force a candidate to exist so find_related_incidents is called
        with patch("incidents.tasks._build_correlation_candidates", return_value=[{"id": 999}]):
            run_incident_triage.apply(args=(incident.id,))

    comment = Comment.objects.get(incident=incident, kind=Comment.KIND_AI_TRIAGE)
    assert comment.body == "Triage completed despite correlation error."
    assert comment.metadata["related_incident_ids"] == []


# ── _clamp_severity unit tests ────────────────────────────────────────────────


def test_clamp_severity_no_change_same():
    from incidents.tasks import _clamp_severity
    assert _clamp_severity("medium", "medium") == "medium"


def test_clamp_severity_1_level_up():
    from incidents.tasks import _clamp_severity
    assert _clamp_severity("low", "medium") == "medium"


def test_clamp_severity_2_levels_up_applied():
    from incidents.tasks import _clamp_severity
    assert _clamp_severity("low", "high") == "high"


def test_clamp_severity_3_levels_up_capped():
    from incidents.tasks import _clamp_severity
    # low(1) → critical(4): delta 3 → capped at 2 → high(3)
    assert _clamp_severity("low", "critical") == "high"


def test_clamp_severity_1_level_down():
    from incidents.tasks import _clamp_severity
    assert _clamp_severity("high", "medium") == "medium"


def test_clamp_severity_2_levels_down_applied():
    from incidents.tasks import _clamp_severity
    assert _clamp_severity("critical", "medium") == "medium"


def test_clamp_severity_3_levels_down_capped():
    from incidents.tasks import _clamp_severity
    # critical(4) → low(1): delta -3 → capped at -2 → medium(2)
    assert _clamp_severity("critical", "low") == "medium"


# ── triage_running / triage_started_at in incident serializer ────────────────


@pytest.mark.django_db
def test_incident_detail_triage_running_false_when_no_lock(admin_client, acme):
    """incident.triage_running is False when no triage lock is set."""
    # Use state="triaged" to avoid triggering the post-save signal that would set the lock
    incident = make_incident(acme, state="triaged")
    response = admin_client.get(f"/api/incidents/{incident.display_id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["triage_running"] is False
    assert data["triage_started_at"] is None


@pytest.mark.django_db
def test_incident_detail_triage_running_true_when_lock_set(admin_client, acme):
    """incident.triage_running is True and triage_started_at is set when lock is held."""
    incident = make_incident(acme)
    from incidents.tasks import acquire_triage_lock, release_triage_lock
    acquire_triage_lock(incident.id)
    try:
        response = admin_client.get(f"/api/incidents/{incident.display_id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["triage_running"] is True
        assert data["triage_started_at"] is not None
    finally:
        release_triage_lock(incident.id)


@pytest.mark.django_db
def test_acquire_triage_lock_stores_iso_timestamp(acme):
    """acquire_triage_lock stores an ISO-format timestamp as the lock value."""
    incident = make_incident(acme)
    from incidents.tasks import acquire_triage_lock, get_triage_lock_started_at, release_triage_lock
    acquire_triage_lock(incident.id)
    try:
        started_at = get_triage_lock_started_at(incident.id)
        assert started_at is not None
        # Should be parseable as an ISO datetime
        from datetime import datetime
        datetime.fromisoformat(started_at)
    finally:
        release_triage_lock(incident.id)


@pytest.mark.django_db
def test_get_triage_lock_started_at_returns_none_when_no_lock(acme):
    """get_triage_lock_started_at returns None when no lock is held."""
    # Use state="triaged" to avoid triggering the post-save signal that would set the lock
    incident = make_incident(acme, state="triaged")
    from incidents.tasks import get_triage_lock_started_at
    assert get_triage_lock_started_at(incident.id) is None


# ── subject_recommendation (#335) ────────────────────────────────────────────


def test_parse_result_subject_recommendation_valid():
    from incidents.llm.gemini import _parse_result
    data = {
        "severity_recommendation": "high",
        "summary": "Phishing attempt detected.",
        "primary_action": "assign_to_analyst",
        "false_positive_confidence": 0.05,
        "subject_recommendation": "phishing",
    }
    result = _parse_result(data, provider="gemini")
    assert result.subject_recommendation == "phishing"


def test_parse_result_subject_recommendation_invalid_cleared():
    from incidents.llm.gemini import _parse_result
    data = {
        "severity_recommendation": "medium",
        "summary": ".",
        "primary_action": "monitor",
        "false_positive_confidence": 0.0,
        "subject_recommendation": "ransomware",
    }
    result = _parse_result(data, provider="gemini")
    assert result.subject_recommendation is None


def test_parse_result_subject_recommendation_missing_is_none():
    from incidents.llm.gemini import _parse_result
    data = {
        "severity_recommendation": "low",
        "summary": ".",
        "primary_action": "monitor",
        "false_positive_confidence": 0.0,
    }
    result = _parse_result(data, provider="gemini")
    assert result.subject_recommendation is None


@pytest.mark.django_db
def test_triage_task_sets_subject_when_recommended(acme):
    from incidents.models import Subject
    incident = make_incident(acme)
    result = _make_triage_result(subject_recommendation="phishing")
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.subject is not None
    assert incident.subject.slug == "phishing"


@pytest.mark.django_db
def test_triage_task_does_not_overwrite_existing_subject(acme):
    from incidents.models import Subject
    malware = Subject.objects.get(slug="malware")
    incident = make_incident(acme)
    incident.subject = malware
    incident.save(update_fields=["subject"])

    result = _make_triage_result(subject_recommendation="phishing")
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.subject.slug == "malware"


@pytest.mark.django_db
def test_triage_task_does_not_set_subject_on_auto_close(acme):
    acme.triage_fp_threshold = 0.95
    acme.save()
    incident = make_incident(acme)
    result = _make_triage_result(
        primary_action="close_as_false_positive",
        false_positive_confidence=0.97,
        subject_recommendation="phishing",
    )
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.subject is None


@pytest.mark.django_db
def test_triage_task_no_subject_when_recommendation_is_none(acme):
    incident = make_incident(acme)
    result = _make_triage_result(subject_recommendation=None)
    _run_task(incident.id, provider_result=result)

    incident.refresh_from_db()
    assert incident.subject is None


# ── source_kind in triage payload ────────────────────────────────────────────


@pytest.mark.django_db
def test_triage_payload_includes_source_kind(acme):
    from incidents.tasks import _build_triage_payload
    incident = make_incident(acme)
    payload = _build_triage_payload(incident)
    assert payload["source_kind"] == "wazuh_event"


@pytest.mark.django_db
def test_triage_payload_source_kind_inbound_email(acme):
    from incidents.tasks import _build_triage_payload
    incident = Incident.objects.create(
        organization=acme,
        title="Phishing email",
        display_id="INC-2026-9991",
        source_kind="inbound_email",
        source_ref={},
        state="new",
        severity="medium",
    )
    payload = _build_triage_payload(incident)
    assert payload["source_kind"] == "inbound_email"


# ── IncidentTriageDebugView ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_debug_endpoint_requires_auth(client, acme):
    incident = make_incident(acme)
    assert client.get(f"/api/incidents/{incident.display_id}/triage/debug/").status_code == 401
    assert client.post(f"/api/incidents/{incident.display_id}/triage/debug/").status_code == 401


@pytest.mark.django_db
def test_debug_endpoint_requires_staff(client, member, acme):
    incident = make_incident(acme)
    client.force_login(member)
    assert client.get(f"/api/incidents/{incident.display_id}/triage/debug/").status_code == 403
    assert client.post(f"/api/incidents/{incident.display_id}/triage/debug/").status_code == 403


@pytest.mark.django_db
def test_debug_get_returns_prompts(client, staff_user, acme):
    incident = make_incident(acme)
    client.force_login(staff_user)
    response = client.get(f"/api/incidents/{incident.display_id}/triage/debug/")
    assert response.status_code == 200
    data = response.json()
    assert "system_prompt" in data
    assert "user_payload" in data
    assert "wazuh_event" in data["user_payload"]


@pytest.mark.django_db
def test_debug_get_uses_source_specific_prompt(client, staff_user, acme):
    incident = Incident.objects.create(
        organization=acme,
        title="Phishing",
        display_id="INC-2026-9992",
        source_kind="inbound_email",
        source_ref={},
        state="new",
        severity="medium",
    )
    client.force_login(staff_user)
    response = client.get(f"/api/incidents/{incident.display_id}/triage/debug/")
    assert response.status_code == 200
    assert "security team mailbox" in response.json()["system_prompt"]


@pytest.mark.django_db
def test_debug_post_runs_llm(client, staff_user, acme):
    incident = make_incident(acme)
    client.force_login(staff_user)

    mock_provider = MagicMock()
    mock_provider.debug_triage_incident.return_value = (
        '{"severity_recommendation":"high","summary":"Test.","primary_action":"escalate","false_positive_confidence":0.1}',
        {
            "severity_recommendation": "high",
            "summary": "Test.",
            "primary_action": "escalate",
            "secondary_action": None,
            "false_positive_confidence": 0.1,
            "subject_recommendation": None,
        },
    )

    with patch("incidents.llm.factory.get_triage_provider", return_value=mock_provider):
        response = client.post(
            f"/api/incidents/{incident.display_id}/triage/debug/",
            data={"system_prompt": "Test prompt", "user_payload": "{}"},
            content_type="application/json",
        )

    assert response.status_code == 200
    data = response.json()
    assert "raw_response" in data
    assert "result" in data
    assert data["result"]["severity_recommendation"] == "high"
    mock_provider.debug_triage_incident.assert_called_once_with("Test prompt", "{}")
