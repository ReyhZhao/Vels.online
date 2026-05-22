import pytest
from django.core.exceptions import ValidationError
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent
from incidents.services.transitions import transition_incident, ALLOWED_TRANSITIONS


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def actor(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def member(db, django_user_model, acme):
    u = django_user_model.objects.create_user(username="member", password="pass")
    OrganizationMembership.objects.create(user=u, organization=acme)
    return u


def make_incident(acme, state="new", closure_reason=None):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=acme,
        title="Test",
        display_id=f"INC-2026-{count + 1:04d}",
        state=state,
        closure_reason=closure_reason,
    )


# ── legal transitions ────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("from_state,to_state", [
    ("new", "triaged"),
    ("new", "in_progress"),
    ("new", "closed"),
    ("triaged", "in_progress"),
    ("triaged", "on_hold"),
    ("in_progress", "on_hold"),
    ("in_progress", "resolved"),
    ("in_progress", "needs_tuning"),
    ("in_progress", "closed"),
    ("on_hold", "in_progress"),
    ("on_hold", "resolved"),
    ("on_hold", "needs_tuning"),
    ("on_hold", "closed"),
    ("needs_tuning", "in_progress"),
    ("needs_tuning", "closed"),
    ("resolved", "in_progress"),
    ("resolved", "closed"),
    ("closed", "in_progress"),
])
def test_legal_transition(from_state, to_state, acme, actor):
    closure_reason = "resolved" if to_state == "closed" else None
    incident = make_incident(acme, state=from_state)
    result = transition_incident(incident, to_state, actor=actor, closure_reason=closure_reason)
    assert result.state == to_state


# ── illegal transitions ──────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("from_state,to_state", [
    ("new", "on_hold"),
    ("new", "resolved"),
    ("new", "needs_tuning"),
    ("triaged", "new"),
    ("triaged", "resolved"),
    ("triaged", "needs_tuning"),
    ("triaged", "closed"),
    ("in_progress", "new"),
    ("in_progress", "triaged"),
    ("on_hold", "new"),
    ("on_hold", "triaged"),
    ("needs_tuning", "new"),
    ("needs_tuning", "triaged"),
    ("needs_tuning", "on_hold"),
    ("needs_tuning", "resolved"),
    ("resolved", "new"),
    ("resolved", "triaged"),
    ("resolved", "on_hold"),
    ("resolved", "needs_tuning"),
    ("closed", "new"),
    ("closed", "triaged"),
    ("closed", "on_hold"),
    ("closed", "needs_tuning"),
    ("closed", "resolved"),
])
def test_illegal_transition_raises(from_state, to_state, acme, actor):
    incident = make_incident(acme, state=from_state)
    with pytest.raises(ValidationError):
        transition_incident(incident, to_state, actor=actor)


# ── closure_reason gate ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_close_without_closure_reason_raises(acme, actor):
    incident = make_incident(acme, state="in_progress")
    with pytest.raises(ValidationError) as exc_info:
        transition_incident(incident, "closed", actor=actor)
    assert "closure_reason" in str(exc_info.value)


@pytest.mark.django_db
@pytest.mark.parametrize("reason", ["resolved", "false_positive", "informational", "accepted_risk"])
def test_close_with_valid_closure_reason(reason, acme, actor):
    incident = make_incident(acme, state="in_progress")
    result = transition_incident(incident, "closed", actor=actor, closure_reason=reason)
    assert result.state == "closed"
    assert result.closure_reason == reason


@pytest.mark.django_db
def test_close_with_duplicate_closure_reason(acme, actor):
    canonical = make_incident(acme, state="in_progress")
    incident = make_incident(acme, state="in_progress")
    result = transition_incident(incident, "closed", actor=actor, closure_reason="duplicate", duplicate_of_id=canonical.pk)
    assert result.state == "closed"
    assert result.closure_reason == "duplicate"


@pytest.mark.django_db
def test_closure_reason_set_on_closed_incident(acme, actor):
    canonical = make_incident(acme, state="in_progress")
    incident = make_incident(acme, state="in_progress")
    transition_incident(incident, "closed", actor=actor, closure_reason="duplicate", duplicate_of_id=canonical.pk)
    incident.refresh_from_db()
    assert incident.closure_reason == "duplicate"


# ── reopen path clears closure_reason ───────────────────────────────────────


@pytest.mark.django_db
def test_reopen_from_closed_clears_closure_reason(acme, actor):
    incident = make_incident(acme, state="closed", closure_reason="resolved")
    transition_incident(incident, "in_progress", actor=actor)
    incident.refresh_from_db()
    assert incident.state == "in_progress"
    assert incident.closure_reason is None


@pytest.mark.django_db
def test_reopen_from_resolved_clears_closure_reason(acme, actor):
    incident = make_incident(acme, state="resolved", closure_reason="resolved")
    incident.closure_reason = "resolved"
    incident.save()
    transition_incident(incident, "in_progress", actor=actor)
    incident.refresh_from_db()
    assert incident.state == "in_progress"
    assert incident.closure_reason is None


@pytest.mark.django_db
def test_needs_tuning_entry_from_in_progress(acme, actor):
    incident = make_incident(acme, state="in_progress")
    result = transition_incident(incident, "needs_tuning", actor=actor)
    assert result.state == "needs_tuning"


@pytest.mark.django_db
def test_needs_tuning_entry_from_on_hold(acme, actor):
    incident = make_incident(acme, state="on_hold")
    result = transition_incident(incident, "needs_tuning", actor=actor)
    assert result.state == "needs_tuning"


@pytest.mark.django_db
def test_needs_tuning_reopen_to_in_progress(acme, actor):
    incident = make_incident(acme, state="needs_tuning")
    result = transition_incident(incident, "in_progress", actor=actor)
    assert result.state == "in_progress"


@pytest.mark.django_db
def test_needs_tuning_close(acme, actor):
    incident = make_incident(acme, state="needs_tuning")
    result = transition_incident(incident, "closed", actor=actor, closure_reason="resolved")
    assert result.state == "closed"


@pytest.mark.django_db
def test_needs_tuning_reopen_clears_closure_reason(acme, actor):
    incident = make_incident(acme, state="needs_tuning", closure_reason="false_positive")
    transition_incident(incident, "in_progress", actor=actor)
    incident.refresh_from_db()
    assert incident.closure_reason is None


@pytest.mark.django_db
@pytest.mark.parametrize("from_state", ["new", "triaged", "resolved", "closed"])
def test_needs_tuning_not_reachable_from_invalid_states(from_state, acme, actor):
    incident = make_incident(acme, state=from_state)
    with pytest.raises(ValidationError):
        transition_incident(incident, "needs_tuning", actor=actor)


# ── event written for every transition ──────────────────────────────────────


@pytest.mark.django_db
def test_transition_writes_incident_updated_event(acme, actor):
    incident = make_incident(acme, state="new")
    transition_incident(incident, "triaged", actor=actor)
    assert IncidentEvent.objects.filter(incident=incident, kind="incident_updated").exists()


@pytest.mark.django_db
def test_transition_event_payload_has_state_change(acme, actor):
    incident = make_incident(acme, state="new")
    transition_incident(incident, "triaged", actor=actor)
    event = IncidentEvent.objects.get(incident=incident, kind="incident_updated")
    assert event.payload["changes"]["state"]["old"] == "new"
    assert event.payload["changes"]["state"]["new"] == "triaged"


@pytest.mark.django_db
def test_close_event_payload_has_closure_reason(acme, actor):
    incident = make_incident(acme, state="in_progress")
    transition_incident(incident, "closed", actor=actor, closure_reason="false_positive")
    event = IncidentEvent.objects.get(incident=incident, kind="incident_updated")
    assert event.payload["changes"]["closure_reason"]["new"] == "false_positive"


@pytest.mark.django_db
def test_reopen_event_payload_has_closure_reason_cleared(acme, actor):
    incident = make_incident(acme, state="closed", closure_reason="duplicate")
    transition_incident(incident, "in_progress", actor=actor)
    event = IncidentEvent.objects.get(incident=incident, kind="incident_updated")
    assert event.payload["changes"]["closure_reason"]["old"] == "duplicate"
    assert event.payload["changes"]["closure_reason"]["new"] is None


@pytest.mark.django_db
def test_transition_event_actor_is_set(acme, actor):
    incident = make_incident(acme, state="new")
    transition_incident(incident, "triaged", actor=actor)
    event = IncidentEvent.objects.get(incident=incident, kind="incident_updated")
    assert event.actor == actor


# ── transition endpoint ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_transition_endpoint_requires_auth(client, acme):
    incident = make_incident(acme)
    response = client.post(
        f"/api/incidents/{incident.display_id}/transition/",
        {"state": "triaged"},
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_transition_endpoint_staff_can_transition(admin_client, acme):
    incident = make_incident(acme)
    response = admin_client.post(
        f"/api/incidents/{incident.display_id}/transition/",
        {"state": "triaged"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["state"] == "triaged"


@pytest.mark.django_db
def test_transition_endpoint_member_forbidden(client, member, acme):
    incident = make_incident(acme)
    client.force_login(member)
    response = client.post(
        f"/api/incidents/{incident.display_id}/transition/",
        {"state": "triaged"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_transition_endpoint_illegal_transition_returns_400(admin_client, acme):
    incident = make_incident(acme, state="new")
    response = admin_client.post(
        f"/api/incidents/{incident.display_id}/transition/",
        {"state": "on_hold"},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_transition_endpoint_close_requires_closure_reason(admin_client, acme):
    incident = make_incident(acme, state="in_progress")
    response = admin_client.post(
        f"/api/incidents/{incident.display_id}/transition/",
        {"state": "closed"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "closure_reason" in response.json()["detail"]


@pytest.mark.django_db
def test_transition_endpoint_close_with_reason(admin_client, acme):
    incident = make_incident(acme, state="in_progress")
    response = admin_client.post(
        f"/api/incidents/{incident.display_id}/transition/",
        {"state": "closed", "closure_reason": "resolved"},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "closed"
    assert data["closure_reason"] == "resolved"


@pytest.mark.django_db
def test_transition_endpoint_missing_state_returns_400(admin_client, acme):
    incident = make_incident(acme)
    response = admin_client.post(
        f"/api/incidents/{incident.display_id}/transition/",
        {},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_patch_rejects_state_change(admin_client, acme):
    incident = make_incident(acme)
    response = admin_client.patch(
        f"/api/incidents/{incident.display_id}/",
        {"state": "triaged"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "transition" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_transition_endpoint_non_member_forbidden(client, acme, django_user_model):
    outsider = django_user_model.objects.create_user(username="outsider", password="pass")
    incident = make_incident(acme)
    client.force_login(outsider)
    response = client.post(
        f"/api/incidents/{incident.display_id}/transition/",
        {"state": "triaged"},
        content_type="application/json",
    )
    assert response.status_code == 404


# ── duplicate closure ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_close_as_duplicate_requires_duplicate_of(acme, actor):
    incident = make_incident(acme, state="in_progress")
    with pytest.raises(ValidationError) as exc_info:
        transition_incident(incident, "closed", actor=actor, closure_reason="duplicate")
    assert "duplicate_of" in str(exc_info.value)


@pytest.mark.django_db
def test_close_as_duplicate_stores_relationship(acme, actor):
    canonical = make_incident(acme, state="in_progress")
    duplicate = make_incident(acme, state="in_progress")
    transition_incident(duplicate, "closed", actor=actor, closure_reason="duplicate", duplicate_of_id=canonical.pk)
    duplicate.refresh_from_db()
    assert duplicate.closure_reason == "duplicate"
    assert duplicate.duplicate_of_id == canonical.pk


@pytest.mark.django_db
def test_close_as_duplicate_self_reference_raises(acme, actor):
    incident = make_incident(acme, state="in_progress")
    with pytest.raises(ValidationError):
        transition_incident(incident, "closed", actor=actor, closure_reason="duplicate", duplicate_of_id=incident.pk)


@pytest.mark.django_db
def test_close_as_duplicate_cross_org_raises(acme, actor, db):
    from security.models import Organization
    other_org = Organization.objects.create(name="Other", slug="other", wazuh_group="other")
    canonical = make_incident(other_org, state="in_progress")
    duplicate = make_incident(acme, state="in_progress")
    with pytest.raises(ValidationError):
        transition_incident(duplicate, "closed", actor=actor, closure_reason="duplicate", duplicate_of_id=canonical.pk)


@pytest.mark.django_db
def test_duplicate_of_on_non_duplicate_closure_raises(acme, actor):
    canonical = make_incident(acme, state="in_progress")
    incident = make_incident(acme, state="in_progress")
    with pytest.raises(ValidationError):
        transition_incident(incident, "closed", actor=actor, closure_reason="resolved", duplicate_of_id=canonical.pk)


@pytest.mark.django_db
def test_reopen_clears_duplicate_of(acme, actor):
    canonical = make_incident(acme, state="in_progress")
    duplicate = make_incident(acme, state="in_progress")
    transition_incident(duplicate, "closed", actor=actor, closure_reason="duplicate", duplicate_of_id=canonical.pk)
    transition_incident(duplicate, "in_progress", actor=actor)
    duplicate.refresh_from_db()
    assert duplicate.duplicate_of_id is None
    assert duplicate.closure_reason is None


@pytest.mark.django_db
def test_close_as_duplicate_nonexistent_target_raises(acme, actor):
    incident = make_incident(acme, state="in_progress")
    with pytest.raises(ValidationError):
        transition_incident(incident, "closed", actor=actor, closure_reason="duplicate", duplicate_of_id=99999)


# ── duplicate endpoint ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_endpoint_close_as_duplicate_requires_duplicate_of(admin_client, acme):
    incident = make_incident(acme, state="in_progress")
    response = admin_client.post(
        f"/api/incidents/{incident.display_id}/transition/",
        {"state": "closed", "closure_reason": "duplicate"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "duplicate_of" in response.json()["detail"]


@pytest.mark.django_db
def test_endpoint_close_as_duplicate_stores_relationship(admin_client, acme):
    canonical = make_incident(acme, state="in_progress")
    duplicate = make_incident(acme, state="in_progress")
    response = admin_client.post(
        f"/api/incidents/{duplicate.display_id}/transition/",
        {"state": "closed", "closure_reason": "duplicate", "duplicate_of": canonical.pk},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["closure_reason"] == "duplicate"
    assert data["duplicate_of"] == canonical.pk
    assert data["duplicate_of_display_id"] == canonical.display_id


@pytest.mark.django_db
def test_endpoint_canonical_shows_duplicates_list(admin_client, acme):
    canonical = make_incident(acme, state="in_progress")
    dup1 = make_incident(acme, state="in_progress")
    dup2 = make_incident(acme, state="in_progress")
    for dup in (dup1, dup2):
        admin_client.post(
            f"/api/incidents/{dup.display_id}/transition/",
            {"state": "closed", "closure_reason": "duplicate", "duplicate_of": canonical.pk},
            content_type="application/json",
        )
    response = admin_client.get(f"/api/incidents/{canonical.display_id}/")
    assert response.status_code == 200
    dup_ids = {d["display_id"] for d in response.json()["duplicates"]}
    assert dup1.display_id in dup_ids
    assert dup2.display_id in dup_ids
