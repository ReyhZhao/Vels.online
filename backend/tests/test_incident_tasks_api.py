import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent, IncidentTemplateApplication, Subject, Task, TaskTemplate, TaskTemplateItem


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def phishing(db):
    return Subject.objects.get(slug="phishing")


@pytest.fixture
def incident(db, acme):
    return Incident.objects.create(
        organization=acme,
        title="Phishing Attack",
        display_id="INC-2026-0001",
        tlp="amber",
    )


@pytest.fixture
def template(db, phishing, django_user_model):
    staff = django_user_model.objects.create_user(username="staff_t", password="pass", is_staff=True)
    t = TaskTemplate.objects.create(name="Phishing Playbook", subject=phishing, created_by=staff)
    TaskTemplateItem.objects.create(template=t, title="Step 1", description="Do step 1", display_order=1)
    TaskTemplateItem.objects.create(template=t, title="Step 2", description="Do step 2", display_order=2)
    return t


# ── GET /api/incidents/<id>/tasks/ ──────────────────────────────────────────


@pytest.mark.django_db
def test_list_tasks_requires_auth(client, incident):
    response = client.get(f"/api/incidents/{incident.display_id}/tasks/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_list_tasks_empty(client, member, incident):
    client.force_login(member)
    response = client.get(f"/api/incidents/{incident.display_id}/tasks/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.django_db
def test_list_tasks_returns_tasks(client, member, incident, template):
    Task.objects.create(incident=incident, title="Adhoc", display_order=1)
    client.force_login(member)
    response = client.get(f"/api/incidents/{incident.display_id}/tasks/")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Adhoc"


# ── POST /api/incidents/<id>/tasks/ (ad-hoc) ─────────────────────────────────


@pytest.mark.django_db
def test_create_adhoc_task_requires_auth(client, incident):
    response = client.post(
        f"/api/incidents/{incident.display_id}/tasks/",
        {"title": "Check logs"},
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_create_adhoc_task_member_allowed(client, member, incident):
    client.force_login(member)
    response = client.post(
        f"/api/incidents/{incident.display_id}/tasks/",
        {"title": "Check logs", "display_order": 1},
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Check logs"
    assert data["template_item"] is None
    assert data["template_name"] is None
    assert data["state"] == "new"
    assert Task.objects.filter(incident=incident, title="Check logs").exists()


@pytest.mark.django_db
def test_create_adhoc_task_emits_event(client, member, incident):
    client.force_login(member)
    client.post(
        f"/api/incidents/{incident.display_id}/tasks/",
        {"title": "Check logs", "display_order": 1},
        content_type="application/json",
    )
    assert IncidentEvent.objects.filter(incident=incident, kind="task_created").exists()


@pytest.mark.django_db
def test_create_adhoc_task_missing_title(client, member, incident):
    client.force_login(member)
    response = client.post(
        f"/api/incidents/{incident.display_id}/tasks/",
        {"display_order": 1},
        content_type="application/json",
    )
    assert response.status_code == 400


# ── POST /api/incidents/<id>/apply-template/ ────────────────────────────────


@pytest.mark.django_db
def test_apply_template_requires_auth(client, incident, template):
    response = client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": template.id},
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_apply_template_creates_tasks(client, member, incident, template):
    client.force_login(member)
    response = client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": template.id},
        content_type="application/json",
    )
    assert response.status_code == 201
    tasks = response.json()
    assert len(tasks) == 2
    titles = [t["title"] for t in tasks]
    assert "Step 1" in titles
    assert "Step 2" in titles
    assert all(t["template_name"] == "Phishing Playbook" for t in tasks)


@pytest.mark.django_db
def test_apply_template_creates_application_record(client, member, incident, template):
    client.force_login(member)
    client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": template.id},
        content_type="application/json",
    )
    assert IncidentTemplateApplication.objects.filter(incident=incident, template=template).exists()


@pytest.mark.django_db
def test_apply_template_emits_event(client, member, incident, template):
    client.force_login(member)
    client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": template.id},
        content_type="application/json",
    )
    assert IncidentEvent.objects.filter(incident=incident, kind="incident_template_applied").exists()


@pytest.mark.django_db
def test_apply_template_idempotency_rejected_when_active(client, member, incident, template):
    client.force_login(member)
    client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": template.id},
        content_type="application/json",
    )
    response = client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": template.id},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_apply_template_reapply_allowed_after_completion(client, member, incident, template):
    client.force_login(member)
    client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": template.id},
        content_type="application/json",
    )
    # Cancel all tasks from this template
    Task.objects.filter(incident=incident, template_item__template=template).update(state="cancelled")
    response = client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": template.id},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert IncidentEvent.objects.filter(incident=incident, kind="incident_template_reapplied").exists()


@pytest.mark.django_db
def test_apply_template_snapshot_semantics(client, member, incident, template):
    """Editing template item after apply does not mutate already-created tasks."""
    client.force_login(member)
    client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": template.id},
        content_type="application/json",
    )
    item = template.items.first()
    original_title = item.title
    item.title = "CHANGED AFTER APPLY"
    item.save()

    task = Task.objects.get(incident=incident, template_item=item)
    assert task.title == original_title


@pytest.mark.django_db
def test_apply_template_missing_template_id(client, member, incident):
    client.force_login(member)
    response = client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_apply_template_not_found(client, member, incident):
    client.force_login(member)
    response = client.post(
        f"/api/incidents/{incident.display_id}/apply-template/",
        {"template_id": 99999},
        content_type="application/json",
    )
    assert response.status_code == 404


# ── GET /api/tasks/<id>/ ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_get_task_requires_auth(client, incident):
    task = Task.objects.create(incident=incident, title="Adhoc", display_order=1)
    response = client.get(f"/api/tasks/{task.id}/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_get_task_returns_data(client, member, incident, template):
    task = Task.objects.create(
        incident=incident,
        template_item=template.items.first(),
        title="Step 1",
        display_order=1,
    )
    client.force_login(member)
    response = client.get(f"/api/tasks/{task.id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Step 1"
    assert data["template_name"] == "Phishing Playbook"


# ── PATCH /api/tasks/<id>/ ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_patch_task_state_change(client, member, incident):
    task = Task.objects.create(incident=incident, title="Adhoc", display_order=1)
    client.force_login(member)
    response = client.patch(
        f"/api/tasks/{task.id}/",
        {"state": "in_progress"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["state"] == "in_progress"
    task.refresh_from_db()
    assert task.state == "in_progress"


@pytest.mark.django_db
def test_patch_task_state_change_emits_event(client, member, incident):
    task = Task.objects.create(incident=incident, title="Adhoc", display_order=1)
    client.force_login(member)
    client.patch(
        f"/api/tasks/{task.id}/",
        {"state": "done"},
        content_type="application/json",
    )
    assert IncidentEvent.objects.filter(incident=incident, kind="task_state_changed").exists()
    event = IncidentEvent.objects.get(incident=incident, kind="task_state_changed")
    assert event.payload["old"] == "new"
    assert event.payload["new"] == "done"


@pytest.mark.django_db
def test_patch_task_sets_closed_at_on_done(client, member, incident):
    task = Task.objects.create(incident=incident, title="Adhoc", display_order=1)
    client.force_login(member)
    response = client.patch(
        f"/api/tasks/{task.id}/",
        {"state": "done"},
        content_type="application/json",
    )
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.closed_at is not None


@pytest.mark.django_db
def test_patch_task_sets_closed_at_on_cancelled(client, member, incident):
    task = Task.objects.create(incident=incident, title="Adhoc", display_order=1)
    client.force_login(member)
    client.patch(f"/api/tasks/{task.id}/", {"state": "cancelled"}, content_type="application/json")
    task.refresh_from_db()
    assert task.closed_at is not None


@pytest.mark.django_db
def test_patch_task_assignee_change_emits_event(admin_client, incident, django_user_model):
    user = django_user_model.objects.create_user(username="bob", password="pass")
    task = Task.objects.create(incident=incident, title="Adhoc", display_order=1)
    admin_client.patch(
        f"/api/tasks/{task.id}/",
        {"assignee": user.id},
        content_type="application/json",
    )
    assert IncidentEvent.objects.filter(incident=incident, kind="task_assignee_changed").exists()


@pytest.mark.django_db
def test_patch_task_requires_auth(client, incident):
    task = Task.objects.create(incident=incident, title="Adhoc", display_order=1)
    response = client.patch(
        f"/api/tasks/{task.id}/",
        {"state": "done"},
        content_type="application/json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_patch_task_not_found(client, member):
    client.force_login(member)
    response = client.patch(
        "/api/tasks/99999/",
        {"state": "done"},
        content_type="application/json",
    )
    assert response.status_code == 404


# ── GET /api/tasks/ (cross-incident task list) ───────────────────────────────


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


def _task(incident, title="Task", state="new", **kwargs):
    return Task.objects.create(incident=incident, title=title, state=state, **kwargs)


@pytest.mark.django_db
def test_task_list_requires_auth(client, incident):
    resp = client.get("/api/tasks/")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_task_list_returns_paginated_structure(client, staff, incident):
    _task(incident, title="Alpha")
    client.force_login(staff)
    resp = client.get("/api/tasks/")
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data and "results" in data and "total_pages" in data


@pytest.mark.django_db
def test_task_list_includes_incident_fields(client, staff, incident):
    _task(incident, title="Alpha")
    client.force_login(staff)
    resp = client.get("/api/tasks/")
    task = resp.json()["results"][0]
    assert task["incident_display_id"] == incident.display_id
    assert task["incident_title"] == incident.title


@pytest.mark.django_db
def test_task_list_scoped_to_visible_incidents(client, acme, contoso, django_user_model):
    user = django_user_model.objects.create_user(username="bob", password="pass")
    OrganizationMembership.objects.create(user=user, organization=acme)

    inc_acme = Incident.objects.create(
        organization=acme, title="Acme Inc", display_id="INC-A-001", tlp="amber"
    )
    inc_contoso = Incident.objects.create(
        organization=contoso, title="Contoso Inc", display_id="INC-C-001", tlp="amber"
    )
    t_acme = _task(inc_acme, title="Acme task")
    t_contoso = _task(inc_contoso, title="Contoso task")

    client.force_login(user)
    resp = client.get("/api/tasks/")
    ids = [r["id"] for r in resp.json()["results"]]
    assert t_acme.id in ids
    assert t_contoso.id not in ids


@pytest.mark.django_db
def test_task_list_q_filter(client, staff, incident):
    _task(incident, title="Phishing review")
    _task(incident, title="Patch servers")
    client.force_login(staff)
    resp = client.get("/api/tasks/?q=phishing")
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Phishing review"


@pytest.mark.django_db
def test_task_list_state_filter(client, staff, incident):
    _task(incident, title="Open task", state="new")
    _task(incident, title="Done task", state="done")
    client.force_login(staff)
    resp = client.get("/api/tasks/?state=done")
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["state"] == "done"


@pytest.mark.django_db
def test_task_list_sort_by_title_asc(client, staff, incident):
    _task(incident, title="Zebra")
    _task(incident, title="Alpha")
    client.force_login(staff)
    resp = client.get("/api/tasks/?sort=title&order=asc")
    titles = [r["title"] for r in resp.json()["results"]]
    assert titles == sorted(titles)


@pytest.mark.django_db
def test_task_list_sort_by_incident_asc(client, staff, acme):
    inc_b = Incident.objects.create(
        organization=acme, title="B", display_id="INC-2026-0002", tlp="amber"
    )
    inc_a = Incident.objects.create(
        organization=acme, title="A", display_id="INC-2026-0001", tlp="amber"
    )
    t_b = _task(inc_b, title="Task B")
    t_a = _task(inc_a, title="Task A")
    client.force_login(staff)
    resp = client.get("/api/tasks/?sort=incident&order=asc")
    ids = [r["id"] for r in resp.json()["results"]]
    assert ids.index(t_a.id) < ids.index(t_b.id)


@pytest.mark.django_db
def test_task_list_default_sort_newest_first(client, staff, incident):
    from datetime import timedelta
    from django.utils import timezone

    old = _task(incident, title="Old")
    Task.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
    new = _task(incident, title="New")

    client.force_login(staff)
    resp = client.get("/api/tasks/")
    ids = [r["id"] for r in resp.json()["results"]]
    assert ids.index(new.id) < ids.index(old.id)
