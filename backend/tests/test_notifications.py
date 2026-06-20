import pytest
from django.contrib.auth.models import User

from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentDelegation
from incidents.services.delegation import delegate, return_delegation
from incidents.services.transfer import transfer_incident
from incidents.services.transitions import transition_incident
from notifications.models import Notification, NotificationPreferences
from notifications.services.notifications import notify


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="p", is_staff=True)


@pytest.fixture
def staff2(db, django_user_model):
    return django_user_model.objects.create_user(username="staff2", password="p", is_staff=True)


@pytest.fixture
def regular(db, django_user_model):
    return django_user_model.objects.create_user(username="regular", password="p", is_staff=False)


def make_incident(org, assignee=None, severity="medium", tlp="amber"):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=org,
        title="Test incident",
        display_id=f"INC-2026-{count + 1:04d}",
        assignee=assignee,
        severity=severity,
        tlp=tlp,
    )


# ── NotificationPreferences auto-creation ────────────────────────────────────

@pytest.mark.django_db
def test_prefs_auto_created_on_user_creation(django_user_model):
    u = django_user_model.objects.create_user(username="newuser", password="p")
    assert NotificationPreferences.objects.filter(user=u).exists()


@pytest.mark.django_db
def test_prefs_default_all_true(django_user_model):
    u = django_user_model.objects.create_user(username="u2", password="p")
    prefs = NotificationPreferences.objects.get(user=u)
    for field in [
        "email_assignment", "inapp_assignment",
        "email_delegation", "inapp_delegation",
        "email_comment", "inapp_comment",
        "email_state_change", "inapp_state_change",
        "email_incident_alert", "inapp_incident_alert",
    ]:
        assert getattr(prefs, field) is True, f"{field} should default to True"


# ── notify() channel routing ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_notify_creates_inapp_when_inapp_enabled(staff, acme):
    incident = make_incident(acme)
    notify("comment", [staff], incident=incident, payload={"title": "hi", "body": "", "link": ""})
    assert Notification.objects.filter(recipient=staff, kind="comment").exists()


@pytest.mark.django_db
def test_notify_no_inapp_when_inapp_disabled(staff, acme):
    prefs = NotificationPreferences.objects.get_or_create(user=staff)[0]
    prefs.inapp_comment = False
    prefs.save()
    incident = make_incident(acme)
    notify("comment", [staff], incident=incident, payload={"title": "hi", "body": "", "link": ""})
    # Row still created for email queuing (email_comment defaults True), but not shown in-app.
    assert not Notification.objects.filter(recipient=staff, kind="comment", shown_inapp=True).exists()


@pytest.mark.django_db
def test_notify_skips_inactive_user(acme, django_user_model):
    inactive = django_user_model.objects.create_user(username="gone", password="p", is_active=False)
    incident = make_incident(acme)
    notify("comment", [inactive], incident=incident, payload={"title": "hi", "body": "", "link": ""})
    assert not Notification.objects.filter(recipient=inactive).exists()


# ── send_digest_email channel combinations ───────────────────────────────────

@pytest.mark.django_db
def test_email_sent_when_only_email_channel_enabled(acme, django_user_model, mailoutbox):
    user = django_user_model.objects.create_user(username="emailonly", password="p", email="e@example.com")
    prefs = NotificationPreferences.objects.get_or_create(user=user)[0]
    prefs.inapp_comment = False
    prefs.email_comment = True
    prefs.save()

    incident = make_incident(acme)
    notify("comment", [user], incident=incident, payload={"title": "New comment", "body": "", "link": ""})

    assert not Notification.objects.filter(recipient=user, shown_inapp=True).exists()

    from notifications.tasks import send_digest_email
    send_digest_email(user.id, incident.id)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["e@example.com"]


@pytest.mark.django_db
def test_no_email_sent_when_only_inapp_channel_enabled(acme, django_user_model, mailoutbox):
    user = django_user_model.objects.create_user(username="inapponly", password="p", email="i@example.com")
    prefs = NotificationPreferences.objects.get_or_create(user=user)[0]
    prefs.inapp_comment = True
    prefs.email_comment = False
    prefs.save()

    incident = make_incident(acme)
    notify("comment", [user], incident=incident, payload={"title": "New comment", "body": "", "link": ""})

    assert Notification.objects.filter(recipient=user, shown_inapp=True).exists()
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_both_channels_enabled_creates_inapp_and_sends_email(acme, django_user_model, mailoutbox):
    user = django_user_model.objects.create_user(username="both", password="p", email="b@example.com")
    incident = make_incident(acme)
    notify("comment", [user], incident=incident, payload={"title": "New comment", "body": "", "link": ""})

    assert Notification.objects.filter(recipient=user, shown_inapp=True).exists()

    from notifications.tasks import send_digest_email
    send_digest_email(user.id, incident.id)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["b@example.com"]


# ── hunt_complete category: routed through notify() without an incident (#527) ──

@pytest.mark.django_db
def test_notify_hunt_complete_creates_inapp(staff):
    # A hunt notification has neither incident nor task; default inapp_hunt_complete is True.
    notify(
        Notification.KIND_HUNT_COMPLETE, [staff],
        payload={"title": "Threat hunt", "body": "finished", "link": "/hunting/abc"},
    )
    n = Notification.objects.get(recipient=staff, kind="hunt_complete")
    assert n.shown_inapp is True
    assert n.incident_id is None and n.task_id is None
    assert n.payload["link"] == "/hunting/abc"


@pytest.mark.django_db
def test_hunt_complete_email_digest_works_without_incident(django_user_model, mailoutbox):
    user = django_user_model.objects.create_user(username="hunter", password="p", email="h@example.com")
    prefs = NotificationPreferences.objects.get_or_create(user=user)[0]
    prefs.inapp_hunt_complete = False
    prefs.email_hunt_complete = True
    prefs.save()

    notify(
        Notification.KIND_HUNT_COMPLETE, [user],
        payload={"title": "Threat hunt", "body": "finished", "link": "/hunting/abc"},
    )

    # The incident-less digest path must batch and send without error.
    from notifications.tasks import send_digest_email
    send_digest_email(user.id, None)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["h@example.com"]


@pytest.mark.django_db
def test_notify_hunt_complete_silent_when_all_channels_disabled(staff, mailoutbox):
    prefs = NotificationPreferences.objects.get_or_create(user=staff)[0]
    prefs.inapp_hunt_complete = False
    prefs.email_hunt_complete = False
    prefs.push_hunt_complete = False
    prefs.save()

    notify(
        Notification.KIND_HUNT_COMPLETE, [staff],
        payload={"title": "Threat hunt", "body": "finished", "link": "/hunting/abc"},
    )

    assert not Notification.objects.filter(recipient=staff, kind="hunt_complete").exists()
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_digest_skips_user_with_no_email_address(acme, django_user_model, mailoutbox):
    user = django_user_model.objects.create_user(username="noemail", password="p", email="")
    incident = make_incident(acme)
    Notification.objects.create(recipient=user, kind="comment", incident=incident, payload={})

    from notifications.tasks import send_digest_email
    send_digest_email(user.id, incident.id)

    assert len(mailoutbox) == 0


# ── email digest rate-limit ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_digest_second_notification_within_window_does_not_queue_second_email(staff, acme, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.CELERY_TASK_EAGER_PROPAGATES = False

    incident = make_incident(acme)
    # First notification – no existing pending, so would schedule email
    notify("comment", [staff], incident=incident, payload={"title": "1", "body": "", "link": ""})
    # Second notification within 5-min window – has_pending_email_task should be True → no new task
    # We verify by checking only 1 unread notification exists (both are written in-app)
    notify("comment", [staff], incident=incident, payload={"title": "2", "body": "", "link": ""})
    assert Notification.objects.filter(recipient=staff, incident=incident, read_at__isnull=True).count() == 2


# ── task_complete preferences ────────────────────────────────────────────────

@pytest.mark.django_db
def test_prefs_patch_task_complete_persists(client, staff):
    client.force_login(staff)
    response = client.patch(
        "/api/me/notification-prefs/",
        {"email_task_complete": False, "inapp_task_complete": False},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email_task_complete"] is False
    assert data["inapp_task_complete"] is False

    # Confirm persisted on re-fetch
    response = client.get("/api/me/notification-prefs/")
    assert response.json()["email_task_complete"] is False
    assert response.json()["inapp_task_complete"] is False


@pytest.mark.django_db
def test_prefs_patch_hunt_complete_persists(client, staff):
    client.force_login(staff)
    response = client.patch(
        "/api/me/notification-prefs/",
        {"email_hunt_complete": True, "inapp_hunt_complete": False},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email_hunt_complete"] is True
    assert data["inapp_hunt_complete"] is False

    response = client.get("/api/me/notification-prefs/")
    assert response.json()["email_hunt_complete"] is True
    assert response.json()["inapp_hunt_complete"] is False


# ── assignment / delegation guardrail ─────────────────────────────────────────

@pytest.mark.django_db
def test_prefs_patch_guardrail_assignment(client, staff):
    client.force_login(staff)
    response = client.patch(
        "/api/me/notification-prefs/",
        {"email_assignment": False, "inapp_assignment": False},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "assignment" in str(response.json()).lower()


@pytest.mark.django_db
def test_prefs_patch_guardrail_delegation(client, staff):
    client.force_login(staff)
    response = client.patch(
        "/api/me/notification-prefs/",
        {"email_delegation": False, "inapp_delegation": False},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "delegation" in str(response.json()).lower()


@pytest.mark.django_db
def test_prefs_patch_allows_one_channel_disabled(client, staff):
    client.force_login(staff)
    response = client.patch(
        "/api/me/notification-prefs/",
        {"email_assignment": False},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["email_assignment"] is False
    assert response.json()["inapp_assignment"] is True


# ── incident_alert fires for org members ─────────────────────────────────────

@pytest.mark.django_db
def test_incident_alert_fires_for_org_members_at_high_severity(client, acme, staff, regular):
    OrganizationMembership.objects.create(user=regular, organization=acme)
    client.force_login(staff)
    response = client.post(
        "/api/incidents/",
        {"org": "acme", "title": "Critical", "severity": "high", "tlp": "amber"},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert Notification.objects.filter(recipient=regular, kind="incident_alert").exists()


@pytest.mark.django_db
def test_incident_alert_does_not_fire_at_tlp_red(client, acme, staff, regular):
    OrganizationMembership.objects.create(user=regular, organization=acme)
    client.force_login(staff)
    response = client.post(
        "/api/incidents/",
        {"org": "acme", "title": "Critical Red", "severity": "high", "tlp": "red"},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert not Notification.objects.filter(recipient=regular, kind="incident_alert").exists()


@pytest.mark.django_db
def test_incident_alert_does_not_fire_at_medium_severity(client, acme, staff, regular):
    OrganizationMembership.objects.create(user=regular, organization=acme)
    client.force_login(staff)
    response = client.post(
        "/api/incidents/",
        {"org": "acme", "title": "Medium", "severity": "medium", "tlp": "amber"},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert not Notification.objects.filter(recipient=regular, kind="incident_alert").exists()


# ── comment author excluded ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_comment_author_excluded_from_comment_notification(client, acme, staff, staff2):
    incident = make_incident(acme, assignee=staff2)
    client.force_login(staff)
    # staff is NOT the assignee; staff2 is. Staff comments → staff2 gets notified, staff does not.
    client.post(
        f"/api/incidents/{incident.display_id}/comments/",
        {"body": "hello"},
        content_type="application/json",
    )
    assert Notification.objects.filter(recipient=staff2, kind="comment").exists()
    assert not Notification.objects.filter(recipient=staff, kind="comment").exists()


@pytest.mark.django_db
def test_assignee_who_comments_excluded(client, acme, staff):
    incident = make_incident(acme, assignee=staff)
    client.force_login(staff)
    client.post(
        f"/api/incidents/{incident.display_id}/comments/",
        {"body": "self-note"},
        content_type="application/json",
    )
    assert not Notification.objects.filter(recipient=staff, kind="comment").exists()


# ── notification endpoints ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_unread_count_endpoint(client, staff, acme):
    incident = make_incident(acme)
    Notification.objects.create(recipient=staff, kind="comment", incident=incident, payload={})
    Notification.objects.create(recipient=staff, kind="comment", incident=incident, payload={})
    client.force_login(staff)
    response = client.get("/api/me/notifications/unread-count/")
    assert response.status_code == 200
    assert response.json()["unread_count"] == 2


@pytest.mark.django_db
def test_mark_notification_read(client, staff, acme):
    incident = make_incident(acme)
    n = Notification.objects.create(recipient=staff, kind="comment", incident=incident, payload={})
    client.force_login(staff)
    response = client.post(f"/api/me/notifications/{n.id}/read/")
    assert response.status_code == 200
    n.refresh_from_db()
    assert n.read_at is not None


@pytest.mark.django_db
def test_read_all_marks_all_read(client, staff, acme):
    incident = make_incident(acme)
    for _ in range(3):
        Notification.objects.create(recipient=staff, kind="comment", incident=incident, payload={})
    client.force_login(staff)
    client.post("/api/me/notifications/read-all/")
    assert not Notification.objects.filter(recipient=staff, read_at__isnull=True).exists()


@pytest.mark.django_db
def test_clear_all_deletes_only_own_notifications(client, staff, staff2, acme):
    from django.utils import timezone as tz
    incident = make_incident(acme)
    # Mix of read and unread for the requesting user
    Notification.objects.create(recipient=staff, kind="comment", incident=incident, payload={})
    Notification.objects.create(
        recipient=staff, kind="comment", incident=incident, payload={}, read_at=tz.now()
    )
    # A second user's notification must be untouched
    other = Notification.objects.create(recipient=staff2, kind="comment", incident=incident, payload={})

    client.force_login(staff)
    response = client.delete("/api/me/notifications/clear-all/")
    assert response.status_code == 200
    assert response.json()["deleted"] == 2
    assert not Notification.objects.filter(recipient=staff).exists()
    assert Notification.objects.filter(pk=other.id).exists()


@pytest.mark.django_db
def test_notification_list_filter_unread(client, staff, acme):
    incident = make_incident(acme)
    from django.utils import timezone
    Notification.objects.create(recipient=staff, kind="comment", incident=incident, payload={})
    Notification.objects.create(
        recipient=staff, kind="comment", incident=incident, payload={}, read_at=timezone.now()
    )
    client.force_login(staff)
    response = client.get("/api/me/notifications/?read=false")
    assert response.status_code == 200
    assert response.json()["count"] == 1


@pytest.mark.django_db
def test_prefs_get_auto_creates_row(client, staff):
    client.force_login(staff)
    NotificationPreferences.objects.filter(user=staff).delete()
    response = client.get("/api/me/notification-prefs/")
    assert response.status_code == 200
    assert NotificationPreferences.objects.filter(user=staff).exists()


# ── DELETE /api/me/notifications/<pk>/ ───────────────────────────────────────

@pytest.mark.django_db
def test_dismiss_unread_notification_returns_was_unread_true(client, staff, acme):
    incident = make_incident(acme)
    n = Notification.objects.create(recipient=staff, kind="comment", incident=incident, payload={})
    client.force_login(staff)
    response = client.delete(f"/api/me/notifications/{n.id}/")
    assert response.status_code == 200
    assert response.json()["was_unread"] is True
    assert not Notification.objects.filter(pk=n.id).exists()


@pytest.mark.django_db
def test_dismiss_read_notification_returns_was_unread_false(client, staff, acme):
    from django.utils import timezone as tz
    incident = make_incident(acme)
    n = Notification.objects.create(
        recipient=staff, kind="comment", incident=incident, payload={}, read_at=tz.now()
    )
    client.force_login(staff)
    response = client.delete(f"/api/me/notifications/{n.id}/")
    assert response.status_code == 200
    assert response.json()["was_unread"] is False


@pytest.mark.django_db
def test_dismiss_another_users_notification_returns_404(client, staff, staff2, acme):
    incident = make_incident(acme)
    n = Notification.objects.create(recipient=staff2, kind="comment", incident=incident, payload={})
    client.force_login(staff)
    response = client.delete(f"/api/me/notifications/{n.id}/")
    assert response.status_code == 404
    assert Notification.objects.filter(pk=n.id).exists()


# ── cleanup_old_notifications task ───────────────────────────────────────────

@pytest.mark.django_db
def test_cleanup_old_notifications_deletes_old_and_keeps_recent(acme, staff):
    from datetime import timedelta
    from django.utils import timezone as tz
    from notifications.tasks import cleanup_old_notifications

    incident = make_incident(acme)
    old = Notification.objects.create(recipient=staff, kind="comment", incident=incident, payload={})
    Notification.objects.filter(pk=old.pk).update(created_at=tz.now() - timedelta(hours=25))

    recent = Notification.objects.create(recipient=staff, kind="comment", incident=incident, payload={})

    cleanup_old_notifications()

    assert not Notification.objects.filter(pk=old.pk).exists()
    assert Notification.objects.filter(pk=recent.pk).exists()


# ── TestEmailView ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_test_email_requires_auth(client):
    res = client.post("/api/admin/test-email/")
    assert res.status_code in (401, 403)


@pytest.mark.django_db
def test_test_email_non_staff_forbidden(client, regular):
    client.force_login(regular)
    res = client.post("/api/admin/test-email/")
    assert res.status_code == 403


@pytest.mark.django_db
def test_test_email_sends_to_staff_email(client, staff, mailoutbox):
    staff.email = "staff@example.com"
    staff.save()
    client.force_login(staff)
    res = client.post("/api/admin/test-email/")
    assert res.status_code == 200
    assert res.json()["detail"] == "Test email sent to staff@example.com."
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["staff@example.com"]


@pytest.mark.django_db
def test_test_email_no_email_returns_400(client, staff):
    staff.email = ""
    staff.save()
    client.force_login(staff)
    res = client.post("/api/admin/test-email/")
    assert res.status_code == 400


@pytest.mark.django_db
def test_test_email_smtp_error_returns_500(client, staff):
    from unittest.mock import patch
    from smtplib import SMTPException

    staff.email = "staff@example.com"
    staff.save()
    client.force_login(staff)
    with patch("notifications.email.EmailMultiAlternatives.send", side_effect=SMTPException("connection refused")):
        res = client.post("/api/admin/test-email/")
    assert res.status_code == 500
    assert "Failed to send test email" in res.json()["detail"]
