import pytest
from django.utils import timezone
from datetime import timedelta
from security.models import Organization, OrganizationMembership
from incidents.models import Comment, Incident, IncidentEvent, Task


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def bob(db, django_user_model):
    return django_user_model.objects.create_user(username="bob", password="pass")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def bob_member(bob, acme):
    OrganizationMembership.objects.create(user=bob, organization=acme)
    return bob


def make_incident(acme, tlp="green"):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=acme,
        title="Test incident",
        display_id=f"INC-TEST-{count + 1}",
        tlp=tlp,
    )


def make_task(incident):
    return Task.objects.create(incident=incident, title="A task")


def make_comment(incident, author, task=None, body="Hello", is_internal=False, minutes_ago=0):
    c = Comment.objects.create(
        incident=incident,
        task=task,
        author=author,
        body=body,
        is_internal=is_internal,
    )
    if minutes_ago:
        Comment.objects.filter(pk=c.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago)
        )
        c.refresh_from_db()
    return c


# ── comment model clean() constraint ─────────────────────────────────────────


@pytest.mark.django_db
def test_comment_task_incident_mismatch_raises(acme, alice):
    inc1 = make_incident(acme)
    inc2 = make_incident(acme)
    task = make_task(inc1)
    c = Comment(incident=inc2, task=task, author=alice, body="bad")
    with pytest.raises(Exception):
        c.clean()


@pytest.mark.django_db
def test_comment_task_incident_match_ok(acme, alice):
    inc = make_incident(acme)
    task = make_task(inc)
    c = Comment(incident=inc, task=task, author=alice, body="ok")
    c.clean()  # should not raise


# ── GET /api/incidents/<id>/comments/ ────────────────────────────────────────


@pytest.mark.django_db
def test_incident_comments_lists_all_including_deleted(admin_client, acme, staff):
    inc = make_incident(acme)
    make_comment(inc, staff, body="visible")
    deleted = make_comment(inc, staff, body="gone")
    deleted.deleted_at = timezone.now()
    deleted.save()

    resp = admin_client.get(f"/api/incidents/{inc.id}/comments/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    # deleted row is present (UI renders [deleted]), body preserved server-side
    deleted_entry = next(c for c in resp.json() if c["deleted_at"] is not None)
    assert deleted_entry["body"] == "gone"


@pytest.mark.django_db
def test_incident_comments_deleted_shows_placeholder(admin_client, acme, staff):
    inc = make_incident(acme)
    deleted = make_comment(inc, staff, body="secret")
    deleted.deleted_at = timezone.now()
    deleted.save()

    resp = admin_client.get(f"/api/incidents/{inc.id}/comments/")
    assert resp.status_code == 200
    # deleted_at is set; body not exposed but deleted_at is truthy
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["deleted_at"] is not None


# ── Visibility: TLP × is_internal × role ─────────────────────────────────────


@pytest.mark.django_db
def test_member_sees_noninternal_at_green(client, acme, member, staff):
    inc = make_incident(acme, tlp="green")
    make_comment(inc, staff, body="public", is_internal=False)
    make_comment(inc, staff, body="secret", is_internal=True)

    client.force_login(member)
    resp = client.get(f"/api/incidents/{inc.id}/comments/")
    assert resp.status_code == 200
    bodies = [c["body"] for c in resp.json()]
    assert "public" in bodies
    assert "secret" not in bodies


@pytest.mark.django_db
def test_member_sees_noninternal_at_white(client, acme, member, staff):
    inc = make_incident(acme, tlp="white")
    make_comment(inc, staff, body="public", is_internal=False)
    make_comment(inc, staff, body="secret", is_internal=True)

    client.force_login(member)
    resp = client.get(f"/api/incidents/{inc.id}/comments/")
    assert resp.status_code == 200
    bodies = [c["body"] for c in resp.json()]
    assert "public" in bodies
    assert "secret" not in bodies


@pytest.mark.django_db
def test_member_sees_no_comments_at_amber(client, acme, member, staff):
    inc = make_incident(acme, tlp="amber")
    make_comment(inc, staff, body="public", is_internal=False)

    client.force_login(member)
    resp = client.get(f"/api/incidents/{inc.id}/comments/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.django_db
def test_staff_sees_all_comments_including_internal(admin_client, acme, staff):
    inc = make_incident(acme, tlp="amber")
    make_comment(inc, staff, body="public", is_internal=False)
    make_comment(inc, staff, body="secret", is_internal=True)

    resp = admin_client.get(f"/api/incidents/{inc.id}/comments/")
    assert resp.status_code == 200
    bodies = [c["body"] for c in resp.json()]
    assert "public" in bodies
    assert "secret" in bodies


# ── POST /api/incidents/<id>/comments/ ───────────────────────────────────────


@pytest.mark.django_db
def test_post_comment_creates_event(admin_client, acme, staff):
    inc = make_incident(acme)
    resp = admin_client.post(
        f"/api/incidents/{inc.id}/comments/",
        {"body": "Test comment", "is_internal": False},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert IncidentEvent.objects.filter(incident=inc, kind="comment_added").exists()


@pytest.mark.django_db
def test_post_comment_internal_flag(admin_client, acme, staff):
    inc = make_incident(acme)
    resp = admin_client.post(
        f"/api/incidents/{inc.id}/comments/",
        {"body": "Internal note", "is_internal": True},
        content_type="application/json",
    )
    assert resp.status_code == 201
    event = IncidentEvent.objects.get(incident=inc, kind="comment_added")
    assert event.payload["is_internal"] is True


# ── GET /api/tasks/<id>/comments/ ────────────────────────────────────────────


@pytest.mark.django_db
def test_task_comments_returned(admin_client, acme, staff):
    inc = make_incident(acme)
    task = make_task(inc)
    make_comment(inc, staff, task=task, body="task comment")

    resp = admin_client.get(f"/api/tasks/{task.id}/comments/")
    assert resp.status_code == 200
    assert any(c["body"] == "task comment" for c in resp.json())


# ── PATCH /api/comments/<id>/ — edit window ───────────────────────────────────


@pytest.mark.django_db
def test_author_can_edit_within_window(client, acme, member):
    inc = make_incident(acme)
    comment = make_comment(inc, member, body="original", minutes_ago=5)

    client.force_login(member)
    resp = client.patch(
        f"/api/comments/{comment.id}/",
        {"body": "edited"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["body"] == "edited"
    assert IncidentEvent.objects.filter(incident=inc, kind="comment_edited").exists()


@pytest.mark.django_db
def test_author_cannot_edit_after_window(client, acme, member):
    inc = make_incident(acme)
    comment = make_comment(inc, member, body="original", minutes_ago=16)

    client.force_login(member)
    resp = client.patch(
        f"/api/comments/{comment.id}/",
        {"body": "too late"},
        content_type="application/json",
    )
    assert resp.status_code == 403
    assert "window" in resp.json()["detail"].lower()


@pytest.mark.django_db
def test_non_author_cannot_edit(client, acme, member, bob_member):
    inc = make_incident(acme)
    comment = make_comment(inc, member, body="original")

    client.force_login(bob_member)
    resp = client.patch(
        f"/api/comments/{comment.id}/",
        {"body": "hijack"},
        content_type="application/json",
    )
    assert resp.status_code == 403


# ── DELETE /api/comments/<id>/ — soft delete ──────────────────────────────────


@pytest.mark.django_db
def test_author_can_soft_delete_within_window(client, acme, member):
    inc = make_incident(acme)
    comment = make_comment(inc, member, minutes_ago=5)

    client.force_login(member)
    resp = client.delete(f"/api/comments/{comment.id}/")
    assert resp.status_code == 204
    comment.refresh_from_db()
    assert comment.deleted_at is not None
    assert IncidentEvent.objects.filter(incident=inc, kind="comment_deleted").exists()


@pytest.mark.django_db
def test_author_cannot_delete_after_window(client, acme, member):
    inc = make_incident(acme)
    comment = make_comment(inc, member, minutes_ago=16)

    client.force_login(member)
    resp = client.delete(f"/api/comments/{comment.id}/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_staff_can_soft_delete_any_comment(client, acme, member, staff):
    inc = make_incident(acme)
    comment = make_comment(inc, member, minutes_ago=60)

    client.force_login(staff)
    resp = client.delete(f"/api/comments/{comment.id}/")
    assert resp.status_code == 204
    comment.refresh_from_db()
    assert comment.deleted_at is not None


@pytest.mark.django_db
def test_soft_delete_preserves_body(client, acme, member, staff):
    inc = make_incident(acme)
    comment = make_comment(inc, member, body="preserved body", minutes_ago=60)

    client.force_login(staff)
    client.delete(f"/api/comments/{comment.id}/")
    comment.refresh_from_db()
    assert comment.body == "preserved body"


@pytest.mark.django_db
def test_cannot_delete_already_deleted(client, acme, staff):
    inc = make_incident(acme)
    comment = make_comment(inc, staff)
    comment.deleted_at = timezone.now()
    comment.save()

    client.force_login(staff)
    resp = client.delete(f"/api/comments/{comment.id}/")
    assert resp.status_code == 400


# ── auth gates ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_unauthenticated_cannot_list_comments(client, acme):
    inc = make_incident(acme)
    resp = client.get(f"/api/incidents/{inc.id}/comments/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_unauthenticated_cannot_post_comment(client, acme):
    inc = make_incident(acme)
    resp = client.post(
        f"/api/incidents/{inc.id}/comments/",
        {"body": "hi"},
        content_type="application/json",
    )
    assert resp.status_code == 403
