import pytest

from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(regular_user, acme):
    OrganizationMembership.objects.create(user=regular_user, organization=acme)
    return regular_user


# ---------------------------------------------------------------- GET /api/security/enrollment/


@pytest.mark.django_db
def test_enrollment_requires_authentication(client, acme):
    response = client.get("/api/security/enrollment/?org=acme")
    assert response.status_code == 401


@pytest.mark.django_db
def test_enrollment_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/enrollment/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
def test_enrollment_missing_org_returns_400(client, acme_member):
    client.force_login(acme_member)
    response = client.get("/api/security/enrollment/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_enrollment_unknown_org_returns_404(client, acme_member):
    client.force_login(acme_member)
    response = client.get("/api/security/enrollment/?org=does-not-exist")
    assert response.status_code == 404


@pytest.mark.django_db
def test_enrollment_contains_wazuh_group(client, acme_member, acme, monkeypatch):
    monkeypatch.setenv("WAZUH_MANAGER_HOST", "wazuh.example.com")
    client.force_login(acme_member)

    response = client.get("/api/security/enrollment/?org=acme")

    assert response.status_code == 200
    data = response.json()
    assert data["wazuh_group"] == "acme"
    assert "acme" in data["install_command"]


@pytest.mark.django_db
def test_enrollment_contains_manager_host(client, acme_member, acme, monkeypatch):
    monkeypatch.setenv("WAZUH_MANAGER_HOST", "wazuh.example.com")
    client.force_login(acme_member)

    response = client.get("/api/security/enrollment/?org=acme")

    data = response.json()
    assert data["manager_host"] == "wazuh.example.com"
    assert "wazuh.example.com" in data["install_command"]


@pytest.mark.django_db
def test_enrollment_admin_can_query_any_org(admin_client, acme, monkeypatch):
    monkeypatch.setenv("WAZUH_MANAGER_HOST", "wazuh.example.com")
    response = admin_client.get("/api/security/enrollment/?org=acme")
    assert response.status_code == 200
