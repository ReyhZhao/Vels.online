import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, Subject, TaskTemplate


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


@pytest.fixture
def phishing(db):
    return Subject.objects.get(slug="phishing")


@pytest.fixture
def malware(db):
    return Subject.objects.get(slug="malware")


# ── GET /api/subjects/ ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_subjects_requires_auth(client):
    response = client.get("/api/subjects/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_list_subjects_returns_all(client, acme_member, phishing, malware):
    client.force_login(acme_member)
    response = client.get("/api/subjects/")
    assert response.status_code == 200
    slugs = [s["slug"] for s in response.json()]
    assert "phishing" in slugs
    assert "malware" in slugs


@pytest.mark.django_db
def test_list_subjects_includes_archived(client, acme_member, phishing):
    phishing.archived = True
    phishing.save()
    client.force_login(acme_member)
    response = client.get("/api/subjects/")
    assert response.status_code == 200
    slugs = [s["slug"] for s in response.json()]
    assert "phishing" in slugs


# ── POST /api/subjects/ ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_subject_requires_staff(client, acme_member):
    client.force_login(acme_member)
    response = client.post("/api/subjects/", {"name": "Ransomware"}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_create_subject_staff_success(admin_client):
    response = admin_client.post("/api/subjects/", {"name": "Ransomware"}, content_type="application/json")
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Ransomware"
    assert data["slug"] == "ransomware"
    assert data["archived"] is False


@pytest.mark.django_db
def test_create_subject_duplicate_name_rejected(admin_client, phishing):
    response = admin_client.post("/api/subjects/", {"name": "Phishing"}, content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_create_subject_missing_name_rejected(admin_client):
    response = admin_client.post("/api/subjects/", {}, content_type="application/json")
    assert response.status_code == 400


# ── GET /api/subjects/<id>/ ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_get_subject_requires_auth(client, phishing):
    response = client.get(f"/api/subjects/{phishing.id}/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_get_subject_returns_detail(client, acme_member, phishing):
    client.force_login(acme_member)
    response = client.get(f"/api/subjects/{phishing.id}/")
    assert response.status_code == 200
    assert response.json()["slug"] == "phishing"


@pytest.mark.django_db
def test_get_subject_not_found(client, acme_member):
    client.force_login(acme_member)
    response = client.get("/api/subjects/99999/")
    assert response.status_code == 404


# ── PATCH /api/subjects/<id>/ ────────────────────────────────────────────────


@pytest.mark.django_db
def test_patch_subject_requires_staff(client, acme_member, phishing):
    client.force_login(acme_member)
    response = client.patch(f"/api/subjects/{phishing.id}/", {"archived": True}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_patch_subject_archive(admin_client, phishing):
    response = admin_client.patch(f"/api/subjects/{phishing.id}/", {"archived": True}, content_type="application/json")
    assert response.status_code == 200
    phishing.refresh_from_db()
    assert phishing.archived is True


@pytest.mark.django_db
def test_patch_subject_update_description(admin_client, phishing):
    response = admin_client.patch(
        f"/api/subjects/{phishing.id}/",
        {"description": "Updated description."},
        content_type="application/json",
    )
    assert response.status_code == 200
    phishing.refresh_from_db()
    assert phishing.description == "Updated description."


@pytest.mark.django_db
def test_patch_subject_rename_updates_slug(admin_client, phishing):
    response = admin_client.patch(
        f"/api/subjects/{phishing.id}/",
        {"name": "Spear Phishing"},
        content_type="application/json",
    )
    assert response.status_code == 200
    phishing.refresh_from_db()
    assert phishing.name == "Spear Phishing"
    assert phishing.slug == "spear-phishing"


@pytest.mark.django_db
def test_patch_subject_rename_collision_rejected(admin_client, phishing, malware):
    response = admin_client.patch(
        f"/api/subjects/{phishing.id}/",
        {"name": "Malware"},
        content_type="application/json",
    )
    assert response.status_code == 400
    phishing.refresh_from_db()
    assert phishing.slug == "phishing"  # unchanged


# ── DELETE /api/subjects/<id>/ ───────────────────────────────────────────────


@pytest.mark.django_db
def test_delete_subject_requires_staff(client, acme_member, phishing):
    client.force_login(acme_member)
    response = client.delete(f"/api/subjects/{phishing.id}/")
    assert response.status_code == 403
    assert Subject.objects.filter(pk=phishing.id).exists()


@pytest.mark.django_db
def test_delete_subject_success(admin_client):
    subject = Subject.objects.create(name="Disposable", slug="disposable")
    response = admin_client.delete(f"/api/subjects/{subject.id}/")
    assert response.status_code == 204
    assert not Subject.objects.filter(pk=subject.id).exists()


@pytest.mark.django_db
def test_delete_subject_blocked_by_task_templates(admin_client, phishing):
    TaskTemplate.objects.create(name="Phishing playbook", subject=phishing)
    response = admin_client.delete(f"/api/subjects/{phishing.id}/")
    assert response.status_code == 409
    assert Subject.objects.filter(pk=phishing.id).exists()


@pytest.mark.django_db
def test_delete_subject_referenced_by_incident_nulls_fk(admin_client, acme):
    subject = Subject.objects.create(name="Standalone", slug="standalone")
    incident = Incident.objects.create(
        display_id="INC-2026-0100",
        organization=acme,
        title="Phishing case",
        source_kind="wazuh_event",
        subject=subject,
    )
    response = admin_client.delete(f"/api/subjects/{subject.id}/")
    assert response.status_code == 204
    incident.refresh_from_db()
    assert incident.subject is None


@pytest.mark.django_db
def test_delete_subject_not_found(admin_client):
    response = admin_client.delete("/api/subjects/99999/")
    assert response.status_code == 404


# ── seed migration check ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_seed_migration_created_starter_subjects():
    slugs = set(Subject.objects.values_list("slug", flat=True))
    assert "phishing" in slugs
    assert "malware" in slugs
    assert "account_compromise" in slugs
    assert "data_exfiltration" in slugs
    assert "policy_violation" in slugs
