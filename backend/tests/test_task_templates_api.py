import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Subject, TaskTemplate, TaskTemplateItem


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def phishing(db):
    return Subject.objects.get(slug="phishing")


@pytest.fixture
def malware(db):
    return Subject.objects.get(slug="malware")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def template(db, phishing, django_user_model):
    staff = django_user_model.objects.create_user(username="staff_t", password="pass", is_staff=True)
    t = TaskTemplate.objects.create(name="Phishing Playbook", subject=phishing, created_by=staff)
    TaskTemplateItem.objects.create(template=t, title="Step 1", display_order=1)
    TaskTemplateItem.objects.create(template=t, title="Step 2", display_order=2)
    return t


# ── GET /api/task-templates/ ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_requires_auth(client):
    response = client.get("/api/task-templates/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_returns_templates(client, member, template):
    client.force_login(member)
    response = client.get("/api/task-templates/")
    assert response.status_code == 200
    names = [t["name"] for t in response.json()]
    assert "Phishing Playbook" in names


@pytest.mark.django_db
def test_list_filter_by_subject(client, member, template, malware):
    other = TaskTemplate.objects.create(name="Malware Playbook", subject=malware)
    client.force_login(member)
    response = client.get(f"/api/task-templates/?subject={malware.id}")
    assert response.status_code == 200
    names = [t["name"] for t in response.json()]
    assert "Malware Playbook" in names
    assert "Phishing Playbook" not in names


@pytest.mark.django_db
def test_list_includes_items(client, member, template):
    client.force_login(member)
    response = client.get("/api/task-templates/")
    data = response.json()
    tmpl = next(t for t in data if t["name"] == "Phishing Playbook")
    assert len(tmpl["items"]) == 2
    assert tmpl["items"][0]["title"] == "Step 1"


# ── POST /api/task-templates/ ────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_requires_staff(client, member, phishing):
    client.force_login(member)
    response = client.post(
        "/api/task-templates/",
        {"name": "My Playbook", "subject": phishing.id},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_create_staff_success(admin_client, phishing):
    response = admin_client.post(
        "/api/task-templates/",
        {"name": "New Playbook", "subject": phishing.id, "description": "Test.", "is_auto_apply": True},
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Playbook"
    assert data["subject_slug"] == "phishing"
    assert data["is_auto_apply"] is True
    assert data["archived"] is False
    assert data["items"] == []


@pytest.mark.django_db
def test_create_missing_name_returns_400(admin_client, phishing):
    response = admin_client.post(
        "/api/task-templates/",
        {"subject": phishing.id},
        content_type="application/json",
    )
    assert response.status_code == 400


# ── GET /api/task-templates/<id>/ ────────────────────────────────────────────


@pytest.mark.django_db
def test_detail_requires_auth(client, template):
    response = client.get(f"/api/task-templates/{template.id}/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_detail_returns_template_with_items(client, member, template):
    client.force_login(member)
    response = client.get(f"/api/task-templates/{template.id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Phishing Playbook"
    assert len(data["items"]) == 2


@pytest.mark.django_db
def test_detail_not_found(client, member):
    client.force_login(member)
    response = client.get("/api/task-templates/99999/")
    assert response.status_code == 404


# ── PATCH /api/task-templates/<id>/ ─────────────────────────────────────────


@pytest.mark.django_db
def test_patch_requires_staff(client, member, template):
    client.force_login(member)
    response = client.patch(
        f"/api/task-templates/{template.id}/",
        {"name": "Updated"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_patch_updates_name(admin_client, template):
    response = admin_client.patch(
        f"/api/task-templates/{template.id}/",
        {"name": "Updated Name"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"
    template.refresh_from_db()
    assert template.name == "Updated Name"


@pytest.mark.django_db
def test_patch_toggle_auto_apply(admin_client, template):
    response = admin_client.patch(
        f"/api/task-templates/{template.id}/",
        {"is_auto_apply": True},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["is_auto_apply"] is True


# ── DELETE /api/task-templates/<id>/ archives, does not delete ───────────────


@pytest.mark.django_db
def test_delete_requires_staff(client, member, template):
    client.force_login(member)
    response = client.delete(f"/api/task-templates/{template.id}/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_delete_archives_template(admin_client, template):
    response = admin_client.delete(f"/api/task-templates/{template.id}/")
    assert response.status_code == 204
    template.refresh_from_db()
    assert template.archived is True
    assert TaskTemplate.objects.filter(pk=template.pk).exists()


@pytest.mark.django_db
def test_delete_does_not_delete_record(admin_client, template):
    admin_client.delete(f"/api/task-templates/{template.id}/")
    assert TaskTemplate.objects.filter(pk=template.pk).exists()


# ── Items sub-resource ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_add_item_requires_staff(client, member, template):
    client.force_login(member)
    response = client.post(
        f"/api/task-templates/{template.id}/items/",
        {"title": "Step 3", "display_order": 3},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_add_item_staff_success(admin_client, template):
    response = admin_client.post(
        f"/api/task-templates/{template.id}/items/",
        {"title": "New step", "description": "Do this.", "display_order": 5},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["title"] == "New step"
    assert template.items.count() == 3


@pytest.mark.django_db
def test_patch_item(admin_client, template):
    item = template.items.first()
    response = admin_client.patch(
        f"/api/task-templates/{template.id}/items/{item.id}/",
        {"title": "Updated step"},
        content_type="application/json",
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.title == "Updated step"


@pytest.mark.django_db
def test_delete_item(admin_client, template):
    item = template.items.first()
    response = admin_client.delete(f"/api/task-templates/{template.id}/items/{item.id}/")
    assert response.status_code == 204
    assert not TaskTemplateItem.objects.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_patch_item_reorder(admin_client, template):
    item = template.items.order_by("display_order").first()
    response = admin_client.patch(
        f"/api/task-templates/{template.id}/items/{item.id}/",
        {"display_order": 99},
        content_type="application/json",
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.display_order == 99


@pytest.mark.django_db
def test_item_belongs_to_template(admin_client, template, phishing, django_user_model):
    other_template = TaskTemplate.objects.create(name="Other", subject=phishing)
    item = template.items.first()
    response = admin_client.patch(
        f"/api/task-templates/{other_template.id}/items/{item.id}/",
        {"title": "hack"},
        content_type="application/json",
    )
    assert response.status_code == 404


# ── Seed migration idempotency ────────────────────────────────────────────────


@pytest.mark.django_db
def test_seed_templates_exist():
    expected_names = [
        "Phishing Response Playbook",
        "Malware Response Playbook",
        "Account Compromise Response Playbook",
        "Data Exfiltration Response Playbook",
        "Policy Violation Response Playbook",
    ]
    for name in expected_names:
        assert TaskTemplate.objects.filter(name=name).exists(), f"Missing: {name}"


@pytest.mark.django_db
def test_seed_templates_are_auto_apply():
    expected_names = [
        "Phishing Response Playbook",
        "Malware Response Playbook",
        "Account Compromise Response Playbook",
        "Data Exfiltration Response Playbook",
        "Policy Violation Response Playbook",
    ]
    for name in expected_names:
        t = TaskTemplate.objects.get(name=name)
        assert t.is_auto_apply is True, f"{name} is not auto_apply"


@pytest.mark.django_db
def test_seed_templates_have_items():
    for template in TaskTemplate.objects.filter(name__endswith="Response Playbook"):
        count = template.items.count()
        assert 5 <= count <= 7, f"{template.name} has {count} items (expected 5-7)"
