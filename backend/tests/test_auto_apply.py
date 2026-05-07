import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, IncidentEvent, Subject, Task, TaskTemplate, TaskTemplateItem


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
def malware(db):
    return Subject.objects.get(slug="malware")


@pytest.fixture
def phishing_auto_template(db, phishing, django_user_model):
    staff = django_user_model.objects.create_user(username="staff_pa", password="pass", is_staff=True)
    t = TaskTemplate.objects.create(
        name="Phishing Auto", subject=phishing, is_auto_apply=True, created_by=staff
    )
    TaskTemplateItem.objects.create(template=t, title="P Step 1", display_order=1)
    TaskTemplateItem.objects.create(template=t, title="P Step 2", display_order=2)
    return t


@pytest.fixture
def phishing_manual_template(db, phishing, django_user_model):
    staff = django_user_model.objects.create_user(username="staff_pm", password="pass", is_staff=True)
    t = TaskTemplate.objects.create(
        name="Phishing Manual", subject=phishing, is_auto_apply=False, created_by=staff
    )
    TaskTemplateItem.objects.create(template=t, title="Manual Step", display_order=1)
    return t


@pytest.fixture
def malware_auto_template(db, malware, django_user_model):
    staff = django_user_model.objects.create_user(username="staff_ma", password="pass", is_staff=True)
    t = TaskTemplate.objects.create(
        name="Malware Auto", subject=malware, is_auto_apply=True, created_by=staff
    )
    TaskTemplateItem.objects.create(template=t, title="M Step 1", display_order=1)
    return t


def make_incident(acme, state="new", subject=None):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=acme,
        title="Test",
        display_id=f"INC-2026-{count + 1:04d}",
        state=state,
        subject=subject,
    )


def patch_subject(client, incident, subject):
    return client.patch(
        f"/api/incidents/{incident.id}/",
        {"subject": subject.id if subject else None},
        content_type="application/json",
    )


# ── setting subject from null ────────────────────────────────────────────────


@pytest.mark.django_db
def test_set_subject_fires_auto_apply(client, member, acme, phishing, phishing_auto_template):
    incident = make_incident(acme)
    client.force_login(member)
    response = patch_subject(client, incident, phishing)
    assert response.status_code == 200
    assert Task.objects.filter(incident=incident, template_item__template=phishing_auto_template).count() == 2


@pytest.mark.django_db
def test_set_subject_does_not_cancel_anything(client, member, acme, phishing, phishing_auto_template):
    incident = make_incident(acme)
    client.force_login(member)
    patch_subject(client, incident, phishing)
    assert not IncidentEvent.objects.filter(incident=incident, kind="tasks_auto_cancelled").exists()


@pytest.mark.django_db
def test_set_subject_manual_template_not_applied(client, member, acme, phishing, phishing_manual_template):
    incident = make_incident(acme)
    client.force_login(member)
    patch_subject(client, incident, phishing)
    # The manual template's item must never appear as a task
    assert not Task.objects.filter(
        incident=incident, template_item__template=phishing_manual_template
    ).exists()


# ── changing subject A → B ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_change_subject_cancels_new_tasks_from_old_subject(
    client, member, acme, phishing, malware, phishing_auto_template, malware_auto_template
):
    incident = make_incident(acme, subject=phishing)
    # Manually create phishing tasks (simulating prior auto-apply)
    item = phishing_auto_template.items.first()
    t1 = Task.objects.create(incident=incident, template_item=item, title=item.title, display_order=1, state="new")
    t2 = Task.objects.create(incident=incident, template_item=phishing_auto_template.items.last(),
                              title="P Step 2", display_order=2, state="new")

    client.force_login(member)
    patch_subject(client, incident, malware)

    t1.refresh_from_db()
    t2.refresh_from_db()
    assert t1.state == "cancelled"
    assert t2.state == "cancelled"
    assert t1.closed_at is not None


@pytest.mark.django_db
def test_change_subject_applies_new_subject_templates(
    client, member, acme, phishing, malware, phishing_auto_template, malware_auto_template
):
    incident = make_incident(acme, subject=phishing)
    client.force_login(member)
    patch_subject(client, incident, malware)
    assert Task.objects.filter(incident=incident, template_item__template=malware_auto_template).count() == 1


@pytest.mark.django_db
def test_change_subject_emits_cancel_summary_event(
    client, member, acme, phishing, malware, phishing_auto_template
):
    incident = make_incident(acme, subject=phishing)
    item = phishing_auto_template.items.first()
    Task.objects.create(incident=incident, template_item=item, title=item.title, display_order=1, state="new")

    client.force_login(member)
    patch_subject(client, incident, malware)

    events = IncidentEvent.objects.filter(incident=incident, kind="tasks_auto_cancelled")
    assert events.count() == 1
    payload = events.first().payload
    assert payload["old_subject_slug"] == "phishing"
    assert payload["count"] == 1


@pytest.mark.django_db
def test_cancel_event_written_exactly_once_per_subject_change(
    client, member, acme, phishing, malware, phishing_auto_template, malware_auto_template
):
    incident = make_incident(acme, subject=phishing)
    item = phishing_auto_template.items.first()
    Task.objects.create(incident=incident, template_item=item, title=item.title, display_order=1)

    client.force_login(member)
    patch_subject(client, incident, malware)
    assert IncidentEvent.objects.filter(incident=incident, kind="tasks_auto_cancelled").count() == 1


# ── protected task states ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_in_progress_tasks_not_cancelled(client, member, acme, phishing, malware, phishing_auto_template):
    incident = make_incident(acme, subject=phishing)
    item = phishing_auto_template.items.first()
    task = Task.objects.create(
        incident=incident, template_item=item, title=item.title, display_order=1, state="in_progress"
    )
    client.force_login(member)
    patch_subject(client, incident, malware)
    task.refresh_from_db()
    assert task.state == "in_progress"


@pytest.mark.django_db
def test_done_tasks_not_cancelled(client, member, acme, phishing, malware, phishing_auto_template):
    incident = make_incident(acme, subject=phishing)
    item = phishing_auto_template.items.first()
    task = Task.objects.create(
        incident=incident, template_item=item, title=item.title, display_order=1, state="done"
    )
    client.force_login(member)
    patch_subject(client, incident, malware)
    task.refresh_from_db()
    assert task.state == "done"


@pytest.mark.django_db
def test_adhoc_tasks_not_cancelled(client, member, acme, phishing, malware):
    incident = make_incident(acme, subject=phishing)
    adhoc = Task.objects.create(incident=incident, template_item=None, title="Adhoc", display_order=1, state="new")
    client.force_login(member)
    patch_subject(client, incident, malware)
    adhoc.refresh_from_db()
    assert adhoc.state == "new"


# ── no cancellation when setting subject for first time ──────────────────────


@pytest.mark.django_db
def test_no_cancel_on_first_subject_set(client, member, acme, phishing, phishing_auto_template):
    incident = make_incident(acme)
    # Ad-hoc task exists before subject is set
    adhoc = Task.objects.create(incident=incident, title="Adhoc", display_order=1, state="new")
    client.force_login(member)
    patch_subject(client, incident, phishing)
    adhoc.refresh_from_db()
    assert adhoc.state == "new"
    assert not IncidentEvent.objects.filter(incident=incident, kind="tasks_auto_cancelled").exists()


# ── idempotency held after A → B → A round-trip ──────────────────────────────


@pytest.mark.django_db
def test_round_trip_idempotency(client, member, acme, phishing, malware, phishing_auto_template, malware_auto_template):
    """A→B→A: second phishing auto-apply is skipped (active tasks exist), no crash."""
    incident = make_incident(acme, subject=phishing)
    # Simulate phishing tasks already applied and left active (in_progress)
    item = phishing_auto_template.items.first()
    Task.objects.create(
        incident=incident, template_item=item, title=item.title, display_order=1, state="in_progress"
    )
    from incidents.models import IncidentTemplateApplication
    IncidentTemplateApplication.objects.create(incident=incident, template=phishing_auto_template)

    client.force_login(member)
    # A → B
    patch_subject(client, incident, malware)
    # B → A: in_progress phishing task is not cancelled, so auto-apply should be skipped
    response = patch_subject(client, incident, phishing)
    assert response.status_code == 200
    # No new phishing tasks created (in_progress task still there, idempotency blocks re-apply)
    assert Task.objects.filter(
        incident=incident, template_item__template=phishing_auto_template, state="new"
    ).count() == 0


# ── clearing subject does not fire auto-apply ─────────────────────────────────


@pytest.mark.django_db
def test_clearing_subject_cancels_new_tasks(client, member, acme, phishing, phishing_auto_template):
    incident = make_incident(acme, subject=phishing)
    item = phishing_auto_template.items.first()
    task = Task.objects.create(
        incident=incident, template_item=item, title=item.title, display_order=1, state="new"
    )
    client.force_login(member)
    response = client.patch(
        f"/api/incidents/{incident.id}/",
        {"subject": None},
        content_type="application/json",
    )
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.state == "cancelled"
