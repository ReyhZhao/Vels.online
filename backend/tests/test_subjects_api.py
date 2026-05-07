import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident, Subject


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
    assert response.status_code == 403


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
    assert response.status_code == 403


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


# ── seed migration check ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_seed_migration_created_starter_subjects():
    slugs = set(Subject.objects.values_list("slug", flat=True))
    assert "phishing" in slugs
    assert "malware" in slugs
    assert "account_compromise" in slugs
    assert "data_exfiltration" in slugs
    assert "policy_violation" in slugs
