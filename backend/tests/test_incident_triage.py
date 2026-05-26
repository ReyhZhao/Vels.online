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


def make_incident(acme, state="new", severity="medium", n=None):
    count = Incident.objects.count() if n is None else n
    return Incident.objects.create(
        organization=acme,
        title="Suspicious login from unknown IP",
        description="Multiple failed SSH attempts",
        display_id=f"INC-2026-{count + 1:04d}",
        source_kind="wazuh_event",
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


# ── run_incident_triage task ──────────────────────────────────────────────────


def _make_triage_result(**kwargs):
    defaults = dict(
        severity_recommendation="medium",
        summary="Normal activity.",
        primary_action="assign_to_analyst",
        secondary_action=None,
        false_positive_confidence=0.1,
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


def test_build_system_prompt_appends_context():
    from incidents.llm.gemini import SYSTEM_PROMPT, _build_system_prompt
    result = _build_system_prompt("treat SSH from 10.0.0.1 as low priority")
    assert result.startswith(SYSTEM_PROMPT)
    assert "--- Organisation context ---" in result
    assert "treat SSH from 10.0.0.1 as low priority" in result


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
        with patch("incidents.signals.run_incident_triage") as mock_task:
            mock_task.delay = MagicMock()
            incident = make_incident(acme, state="new")
            mock_lock.assert_called_once_with(incident.id)
            mock_task.delay.assert_called_once_with(incident.id)


@pytest.mark.django_db
def test_signal_does_not_enqueue_for_non_new_state(acme):
    with patch("incidents.signals.acquire_triage_lock", return_value=True):
        with patch("incidents.signals.run_incident_triage") as mock_task:
            mock_task.delay = MagicMock()
            make_incident(acme, state="triaged")
            mock_task.delay.assert_not_called()


@pytest.mark.django_db
def test_signal_does_not_enqueue_when_lock_taken(acme):
    with patch("incidents.signals.acquire_triage_lock", return_value=False):
        with patch("incidents.signals.run_incident_triage") as mock_task:
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
