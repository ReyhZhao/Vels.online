import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from signups.models import INVITE_TTL_DAYS, InvalidTransition, SignupRequest

_TOKEN = uuid.uuid4()
_GROUP_PK = "group-pk-abc"


@pytest.fixture
def pending(db):
    return SignupRequest.objects.create(
        email="alice@example.com",
        full_name="Alice Smith",
        org_name="Acme Corp",
        intended_use="Security monitoring",
    )


# ── approve (pending → approved) ─────────────────────────────────────────────


@pytest.mark.django_db
def test_approve_sets_status_and_provisioning_fields(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    assert pending.status == SignupRequest.STATUS_APPROVED
    assert pending.approved_org_name == "Acme Corp"
    assert pending.org_slug == "acme-corp"
    assert pending.authentik_group_pk == _GROUP_PK
    assert pending.invite_token == _TOKEN


@pytest.mark.django_db
def test_approve_sets_invite_expires_at_to_7_days(pending):
    before = timezone.now()
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    after = timezone.now()

    assert pending.invite_expires_at is not None
    expected_min = before + timedelta(days=INVITE_TTL_DAYS)
    expected_max = after + timedelta(days=INVITE_TTL_DAYS)
    assert expected_min <= pending.invite_expires_at <= expected_max


@pytest.mark.django_db
def test_approve_sets_actioned_at(pending):
    before = timezone.now()
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    assert pending.actioned_at >= before


@pytest.mark.django_db
def test_approve_from_approved_raises(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    with pytest.raises(InvalidTransition):
        pending.approve("Acme Corp", "acme-corp", _GROUP_PK, uuid.uuid4())


@pytest.mark.django_db
def test_approve_from_rejected_raises(pending):
    pending.reject("spam")
    with pytest.raises(InvalidTransition):
        pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)


@pytest.mark.django_db
def test_approve_from_completed_raises(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.complete()
    with pytest.raises(InvalidTransition):
        pending.approve("Acme Corp", "acme-corp", _GROUP_PK, uuid.uuid4())


# ── reject (pending → rejected) ──────────────────────────────────────────────


@pytest.mark.django_db
def test_reject_sets_status_and_reason(pending):
    pending.reject("spam", note="Looks fake", send_email=False)
    assert pending.status == SignupRequest.STATUS_REJECTED
    assert pending.rejection_reason == "spam"
    assert pending.rejection_note == "Looks fake"
    assert pending.send_rejection_email is False


@pytest.mark.django_db
def test_reject_defaults_send_email_true(pending):
    pending.reject("other")
    assert pending.send_rejection_email is True


@pytest.mark.django_db
def test_reject_sets_actioned_at(pending):
    before = timezone.now()
    pending.reject("spam")
    assert pending.actioned_at >= before


@pytest.mark.django_db
def test_reject_from_approved_raises(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    with pytest.raises(InvalidTransition):
        pending.reject("spam")


@pytest.mark.django_db
def test_reject_from_expired_raises(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.expire()
    with pytest.raises(InvalidTransition):
        pending.reject("spam")


# ── complete (approved → completed) ──────────────────────────────────────────


@pytest.mark.django_db
def test_complete_sets_status(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.complete()
    assert pending.status == SignupRequest.STATUS_COMPLETED


@pytest.mark.django_db
def test_complete_from_pending_raises(pending):
    with pytest.raises(InvalidTransition):
        pending.complete()


@pytest.mark.django_db
def test_complete_from_rejected_raises(pending):
    pending.reject("spam")
    with pytest.raises(InvalidTransition):
        pending.complete()


@pytest.mark.django_db
def test_complete_from_expired_raises(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.expire()
    with pytest.raises(InvalidTransition):
        pending.complete()


# ── expire (approved → expired) ──────────────────────────────────────────────


@pytest.mark.django_db
def test_expire_sets_status(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.expire()
    assert pending.status == SignupRequest.STATUS_EXPIRED


@pytest.mark.django_db
def test_expire_from_pending_raises(pending):
    with pytest.raises(InvalidTransition):
        pending.expire()


@pytest.mark.django_db
def test_expire_from_completed_raises(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.complete()
    with pytest.raises(InvalidTransition):
        pending.expire()


# ── resend (expired → approved) ──────────────────────────────────────────────


@pytest.mark.django_db
def test_resend_sets_status_and_new_token(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.expire()
    new_token = uuid.uuid4()
    pending.resend(new_token)
    assert pending.status == SignupRequest.STATUS_APPROVED
    assert pending.invite_token == new_token


@pytest.mark.django_db
def test_resend_resets_invite_expires_at(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.expire()
    before = timezone.now()
    pending.resend(uuid.uuid4())
    after = timezone.now()

    expected_min = before + timedelta(days=INVITE_TTL_DAYS)
    expected_max = after + timedelta(days=INVITE_TTL_DAYS)
    assert expected_min <= pending.invite_expires_at <= expected_max


@pytest.mark.django_db
def test_resend_sets_actioned_at(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.expire()
    before = timezone.now()
    pending.resend(uuid.uuid4())
    assert pending.actioned_at >= before


@pytest.mark.django_db
def test_resend_from_pending_raises(pending):
    with pytest.raises(InvalidTransition):
        pending.resend(uuid.uuid4())


@pytest.mark.django_db
def test_resend_from_approved_raises(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    with pytest.raises(InvalidTransition):
        pending.resend(uuid.uuid4())


@pytest.mark.django_db
def test_resend_from_completed_raises(pending):
    pending.approve("Acme Corp", "acme-corp", _GROUP_PK, _TOKEN)
    pending.complete()
    with pytest.raises(InvalidTransition):
        pending.resend(uuid.uuid4())
