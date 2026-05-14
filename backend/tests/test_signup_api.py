from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from security.models import Organization, OrganizationMembership
from django.core import mail

from signups.models import SignupRequest
from signups.serializers import REJECTION_REASONS

_VALID_REASON = REJECTION_REASONS[0]  # "Unable to verify organisation"

# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def bypass_throttle(monkeypatch, request):
    if request.node.get_closest_marker("use_real_throttle"):
        return
    from signups.views import SignupThrottle

    monkeypatch.setattr(SignupThrottle, "allow_request", lambda self, request, view: True)


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(
        username="staff", password="pass", email="staff@example.com", is_staff=True
    )


@pytest.fixture
def anon_client(client):
    return client


@pytest.fixture
def staff_client(client, staff):
    client.force_login(staff)
    return client


SUBMIT_PAYLOAD = {
    "email": "alice@example.com",
    "full_name": "Alice Smith",
    "org_name": "Acme Corp",
    "intended_use": "Security monitoring",
    "cf_turnstile_response": "test-token",
}


def _mock_turnstile_ok():
    return patch("signups.views.verify_turnstile")


def _mock_turnstile_fail():
    from rest_framework.exceptions import ValidationError

    return patch("signups.views.verify_turnstile", side_effect=ValidationError("fail"))


_FAKE_INV_UUID = "12345678-1234-5678-1234-567812345678"
_FAKE_GROUP_PK = "87654321-4321-8765-4321-876543218765"


def _mock_authentik():
    mock = MagicMock()
    mock.return_value.create_group.return_value = _FAKE_GROUP_PK
    mock.return_value.create_invitation.return_value = {
        "pk": _FAKE_INV_UUID,
        "token": _FAKE_INV_UUID,
    }
    mock.return_value.build_invite_url.return_value = (
        f"https://auth.example.com/if/flow/enroll/?itoken={_FAKE_INV_UUID}"
    )
    mock.return_value.delete_group.return_value = None
    mock.return_value.delete_invitation.return_value = None
    return patch("signups.views.AuthentikClient", mock)


# ── POST /api/signups/ (public submission) ────────────────────────────────────


@pytest.mark.django_db
def test_submit_creates_pending_request(anon_client):
    with _mock_turnstile_ok(), patch("signups.views.send_admin_notification_email"):
        resp = anon_client.post(
            "/api/signups/", data=SUBMIT_PAYLOAD, content_type="application/json"
        )
    assert resp.status_code == 200
    assert SignupRequest.objects.filter(email="alice@example.com", status="pending").exists()


@pytest.mark.django_db
def test_submit_normalises_email_to_lowercase(anon_client):
    payload = {**SUBMIT_PAYLOAD, "email": "ALICE@EXAMPLE.COM"}
    with _mock_turnstile_ok(), patch("signups.views.send_admin_notification_email"):
        anon_client.post("/api/signups/", data=payload, content_type="application/json")
    assert SignupRequest.objects.filter(email="alice@example.com").exists()


@pytest.mark.django_db
def test_submit_duplicate_pending_returns_200_without_new_record(anon_client):
    SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    with _mock_turnstile_ok():
        resp = anon_client.post(
            "/api/signups/", data=SUBMIT_PAYLOAD, content_type="application/json"
        )
    assert resp.status_code == 200
    assert SignupRequest.objects.count() == 1  # no new record


@pytest.mark.django_db
def test_submit_duplicate_approved_returns_200_without_new_record(anon_client):
    SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme",
        intended_use="...",
        status=SignupRequest.STATUS_APPROVED,
    )
    with _mock_turnstile_ok():
        resp = anon_client.post(
            "/api/signups/", data=SUBMIT_PAYLOAD, content_type="application/json"
        )
    assert resp.status_code == 200
    assert SignupRequest.objects.count() == 1


@pytest.mark.django_db
def test_submit_rejected_within_cooldown_is_blocked(anon_client):
    SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme",
        intended_use="...",
        status=SignupRequest.STATUS_REJECTED,
        actioned_at=timezone.now() - timedelta(hours=2),
    )
    with _mock_turnstile_ok():
        resp = anon_client.post(
            "/api/signups/", data=SUBMIT_PAYLOAD, content_type="application/json"
        )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_submit_rejected_after_cooldown_is_allowed(anon_client):
    SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme",
        intended_use="...",
        status=SignupRequest.STATUS_REJECTED,
        actioned_at=timezone.now() - timedelta(hours=25),
    )
    with _mock_turnstile_ok(), patch("signups.views.send_admin_notification_email"):
        resp = anon_client.post(
            "/api/signups/", data=SUBMIT_PAYLOAD, content_type="application/json"
        )
    assert resp.status_code == 200
    assert SignupRequest.objects.filter(status="pending").exists()


@pytest.mark.use_real_throttle
@pytest.mark.django_db
def test_rate_limit_blocks_fourth_submission_from_same_ip(anon_client):
    from django.core.cache import cache

    cache.clear()  # ensure clean throttle state

    with _mock_turnstile_ok(), patch("signups.views.send_admin_notification_email"):
        for i in range(3):
            payload = {**SUBMIT_PAYLOAD, "email": f"user{i}@example.com"}
            resp = anon_client.post("/api/signups/", data=payload, content_type="application/json")
            assert resp.status_code == 200, f"Request {i + 1} should have been allowed"

    # Fourth request from the same IP should be throttled
    with _mock_turnstile_ok():
        resp = anon_client.post(
            "/api/signups/",
            data={**SUBMIT_PAYLOAD, "email": "user4@example.com"},
            content_type="application/json",
        )
    assert resp.status_code == 429


@pytest.mark.django_db
def test_submit_honeypot_silently_succeeds_without_record(anon_client):
    payload = {**SUBMIT_PAYLOAD, "website": "http://spam.example.com"}
    with _mock_turnstile_ok():
        resp = anon_client.post("/api/signups/", data=payload, content_type="application/json")
    assert resp.status_code == 200
    assert SignupRequest.objects.count() == 0


@pytest.mark.django_db
def test_submit_turnstile_failure_blocks_submission(anon_client):
    with _mock_turnstile_fail():
        resp = anon_client.post(
            "/api/signups/", data=SUBMIT_PAYLOAD, content_type="application/json"
        )
    assert resp.status_code == 400
    assert SignupRequest.objects.count() == 0


# ── GET /api/signups/ (staff list) ───────────────────────────────────────────


@pytest.mark.django_db
def test_list_requires_staff(anon_client, db):
    resp = anon_client.get("/api/signups/")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_list_returns_all_requests(staff_client):
    SignupRequest.objects.create(
        email="a@example.com", full_name="A", org_name="A Corp", intended_use="...", status="pending"
    )
    SignupRequest.objects.create(
        email="b@example.com", full_name="B", org_name="B Corp", intended_use="...", status="approved"
    )
    resp = staff_client.get("/api/signups/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.django_db
def test_list_filters_by_status(staff_client):
    SignupRequest.objects.create(
        email="a@example.com", full_name="A", org_name="A Corp", intended_use="...", status="pending"
    )
    SignupRequest.objects.create(
        email="b@example.com", full_name="B", org_name="B Corp", intended_use="...", status="approved"
    )
    resp = staff_client.get("/api/signups/?status=pending")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"


# ── POST /api/signups/<id>/approve/ ──────────────────────────────────────────


@pytest.mark.django_db
def test_approve_creates_org_and_provisioning(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    with _mock_authentik(), patch("signups.views.send_invite_email"):
        resp = staff_client.post(
            f"/api/signups/{req.pk}/approve/", data={}, content_type="application/json"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["org_slug"] == "acme-corp"
    assert Organization.objects.filter(slug="acme-corp").exists()


@pytest.mark.django_db
def test_approve_with_custom_name_uses_override(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    with _mock_authentik(), patch("signups.views.send_invite_email"):
        resp = staff_client.post(
            f"/api/signups/{req.pk}/approve/",
            data={"approved_org_name": "Acme Renamed"},
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert resp.json()["approved_org_name"] == "Acme Renamed"
    assert Organization.objects.filter(slug="acme-renamed").exists()


@pytest.mark.django_db
def test_approve_conflict_returns_409(staff_client):
    Organization.objects.create(name="Existing Co", slug="acme-corp", wazuh_group="acme-corp")
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    with _mock_authentik():
        resp = staff_client.post(
            f"/api/signups/{req.pk}/approve/", data={}, content_type="application/json"
        )
    assert resp.status_code == 409
    assert resp.json()["conflict"] is True


@pytest.mark.django_db
def test_approve_conflict_resolved_with_approved_org_name(staff_client):
    Organization.objects.create(name="Existing Co", slug="acme-corp", wazuh_group="acme-corp")
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    with _mock_authentik(), patch("signups.views.send_invite_email"):
        resp = staff_client.post(
            f"/api/signups/{req.pk}/approve/",
            data={"approved_org_name": "Acme New"},
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert Organization.objects.filter(slug="acme-new").exists()


@pytest.mark.django_db
def test_approve_sends_invite_email(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    with _mock_authentik(), patch("signups.views.send_invite_email") as mock_task:
        staff_client.post(
            f"/api/signups/{req.pk}/approve/", data={}, content_type="application/json"
        )
    mock_task.delay.assert_called_once_with(req.pk)


@pytest.mark.django_db
def test_approve_requires_staff(anon_client, db):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    resp = anon_client.post(
        f"/api/signups/{req.pk}/approve/", data={}, content_type="application/json"
    )
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_approve_authentik_failure_rolls_back(staff_client):
    from signups.authentik import AuthentikAPIError

    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    mock = MagicMock()
    mock.return_value.create_group.return_value = _FAKE_GROUP_PK
    mock.return_value.create_invitation.side_effect = AuthentikAPIError(500, "internal error")
    mock.return_value.delete_group.return_value = None

    with patch("signups.views.AuthentikClient", mock):
        resp = staff_client.post(
            f"/api/signups/{req.pk}/approve/", data={}, content_type="application/json"
        )

    assert resp.status_code == 502
    mock.return_value.delete_group.assert_called_once_with(_FAKE_GROUP_PK)
    req.refresh_from_db()
    assert req.status == SignupRequest.STATUS_PENDING
    assert not Organization.objects.filter(slug="acme-corp").exists()


@pytest.mark.django_db
def test_approve_non_pending_returns_400(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_APPROVED,
    )
    resp = staff_client.post(
        f"/api/signups/{req.pk}/approve/", data={}, content_type="application/json"
    )
    assert resp.status_code == 400


# ── POST /api/signups/<id>/reject/ ────────────────────────────────────────────


@pytest.mark.django_db
def test_reject_sets_status_and_reason(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    with patch("signups.views.send_rejection_email_task"):
        resp = staff_client.post(
            f"/api/signups/{req.pk}/reject/",
            data={"rejection_reason": _VALID_REASON, "rejection_note": "Looks fake", "send_rejection_email": True},
            content_type="application/json",
        )
    assert resp.status_code == 200
    req.refresh_from_db()
    assert req.status == SignupRequest.STATUS_REJECTED
    assert req.rejection_reason == _VALID_REASON


@pytest.mark.django_db
def test_reject_with_send_email_true_enqueues_task(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    with patch("signups.views.send_rejection_email_task") as mock_task:
        staff_client.post(
            f"/api/signups/{req.pk}/reject/",
            data={"rejection_reason": _VALID_REASON, "send_rejection_email": True},
            content_type="application/json",
        )
    mock_task.delay.assert_called_once_with(req.pk)


@pytest.mark.django_db
def test_reject_with_send_email_false_skips_task(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    with patch("signups.views.send_rejection_email_task") as mock_task:
        staff_client.post(
            f"/api/signups/{req.pk}/reject/",
            data={"rejection_reason": _VALID_REASON, "send_rejection_email": False},
            content_type="application/json",
        )
    mock_task.delay.assert_not_called()


@pytest.mark.django_db
def test_reject_requires_staff(anon_client, db):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    resp = anon_client.post(
        f"/api/signups/{req.pk}/reject/",
        data={"rejection_reason": _VALID_REASON},
        content_type="application/json",
    )
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_reject_non_pending_returns_400(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_REJECTED,
        rejection_reason=_VALID_REASON,
    )
    resp = staff_client.post(
        f"/api/signups/{req.pk}/reject/",
        data={"rejection_reason": _VALID_REASON},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_reject_invalid_reason_returns_400(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    resp = staff_client.post(
        f"/api/signups/{req.pk}/reject/",
        data={"rejection_reason": "spam"},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_reject_email_contains_reason_and_note():
    from signups.tasks import send_rejection_email_task

    note = "Please reapply once documentation is available."
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_REJECTED,
        rejection_reason=_VALID_REASON,
        rejection_note=note,
    )
    send_rejection_email_task(req.pk)
    assert len(mail.outbox) == 1
    body = mail.outbox[0].body
    assert _VALID_REASON in body
    assert note in body


# ── DELETE /api/signups/<id>/ ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_delete_removes_record_and_deprovisions(staff_client):
    org = Organization.objects.create(name="Acme Corp", slug="acme-corp", wazuh_group="acme-corp")
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_APPROVED,
        authentik_group_pk="group-uuid-123",
        org_slug="acme-corp",
    )
    with _mock_authentik():
        resp = staff_client.delete(f"/api/signups/{req.pk}/")
    assert resp.status_code == 204
    assert not SignupRequest.objects.filter(pk=req.pk).exists()
    assert not Organization.objects.filter(slug="acme-corp").exists()


# ── Celery task: expire_stale_invites ─────────────────────────────────────────


@pytest.mark.django_db
def test_expire_stale_invites_marks_expired():
    from signups.tasks import expire_stale_invites

    old = SignupRequest.objects.create(
        email="old@example.com",
        full_name="Old",
        org_name="Old Co",
        intended_use="...",
        status=SignupRequest.STATUS_APPROVED,
        invite_expires_at=timezone.now() - timedelta(days=1),
    )
    fresh = SignupRequest.objects.create(
        email="fresh@example.com",
        full_name="Fresh",
        org_name="Fresh Co",
        intended_use="...",
        status=SignupRequest.STATUS_APPROVED,
        invite_expires_at=timezone.now() + timedelta(days=3),
    )

    expire_stale_invites()

    old.refresh_from_db()
    fresh.refresh_from_db()
    assert old.status == SignupRequest.STATUS_EXPIRED
    assert fresh.status == SignupRequest.STATUS_APPROVED


# ── Signal: signup completion on first login ──────────────────────────────────


@pytest.mark.django_db
def test_first_login_completes_signup_request(django_user_model):
    from security.signals import sync_org_memberships

    org = Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_APPROVED,
        org_slug="acme",
    )
    user = django_user_model.objects.create_user(username="alice")

    sync_org_memberships(user, ["customer:acme"])

    req.refresh_from_db()
    assert req.status == SignupRequest.STATUS_COMPLETED


@pytest.mark.django_db
def test_subsequent_login_does_not_re_complete_request(django_user_model):
    from security.signals import sync_org_memberships

    org = Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")
    user = django_user_model.objects.create_user(username="alice")
    OrganizationMembership.objects.create(user=user, organization=org)

    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_COMPLETED,
        org_slug="acme",
    )

    sync_org_memberships(user, ["customer:acme"])

    req.refresh_from_db()
    assert req.status == SignupRequest.STATUS_COMPLETED  # unchanged


# ── GET /api/signups/pending-count/ ──────────────────────────────────────────


@pytest.mark.django_db
def test_pending_count_returns_correct_number(staff_client):
    SignupRequest.objects.create(
        email="a@example.com", full_name="A", org_name="A", intended_use="...", status="pending"
    )
    SignupRequest.objects.create(
        email="b@example.com", full_name="B", org_name="B", intended_use="...", status="pending"
    )
    SignupRequest.objects.create(
        email="c@example.com", full_name="C", org_name="C", intended_use="...", status="approved"
    )
    resp = staff_client.get("/api/signups/pending-count/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


# ── POST /api/signups/<id>/resend/ ───────────────────────────────────────────


@pytest.mark.django_db
def test_resend_on_expired_transitions_to_approved(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_EXPIRED,
        org_slug="acme-corp",
        approved_org_name="Acme Corp",
        authentik_group_pk=_FAKE_GROUP_PK,
    )
    with _mock_authentik(), patch("signups.views.send_invite_email") as mock_task:
        resp = staff_client.post(
            f"/api/signups/{req.pk}/resend/", data={}, content_type="application/json"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["invite_token"] == _FAKE_INV_UUID
    mock_task.delay.assert_called_once_with(req.pk)


@pytest.mark.django_db
def test_resend_on_approved_refreshes_token(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_APPROVED,
        org_slug="acme-corp",
        approved_org_name="Acme Corp",
        authentik_group_pk=_FAKE_GROUP_PK,
    )
    with _mock_authentik(), patch("signups.views.send_invite_email") as mock_task:
        resp = staff_client.post(
            f"/api/signups/{req.pk}/resend/", data={}, content_type="application/json"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["invite_token"] == _FAKE_INV_UUID
    mock_task.delay.assert_called_once_with(req.pk)


@pytest.mark.django_db
def test_resend_on_invalid_state_returns_400(staff_client):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_PENDING,
    )
    resp = staff_client.post(
        f"/api/signups/{req.pk}/resend/", data={}, content_type="application/json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_resend_requires_staff(anon_client, db):
    req = SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice",
        org_name="Acme Corp",
        intended_use="...",
        status=SignupRequest.STATUS_EXPIRED,
        org_slug="acme-corp",
        approved_org_name="Acme Corp",
    )
    resp = anon_client.post(
        f"/api/signups/{req.pk}/resend/", data={}, content_type="application/json"
    )
    assert resp.status_code in (401, 403)
