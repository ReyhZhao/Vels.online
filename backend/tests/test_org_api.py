from unittest.mock import patch

import pytest

from security.models import Organization, OrganizationMembership
from security.wazuh import WazuhAPIError


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


# ---------------------------------------------------------------- GET /api/security/organizations/


@pytest.mark.django_db
def test_get_orgs_requires_authentication(client):
    response = client.get("/api/security/organizations/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_sees_all_orgs(admin_client, acme, contoso):
    response = admin_client.get("/api/security/organizations/")
    assert response.status_code == 200
    slugs = [o["slug"] for o in response.json()]
    assert "acme" in slugs
    assert "contoso" in slugs


@pytest.mark.django_db
def test_regular_user_sees_only_their_orgs(client, regular_user, acme, contoso):
    OrganizationMembership.objects.create(user=regular_user, organization=acme)
    client.force_login(regular_user)

    response = client.get("/api/security/organizations/")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["slug"] == "acme"


@pytest.mark.django_db
def test_regular_user_with_no_orgs_sees_empty_list(client, regular_user, acme):
    client.force_login(regular_user)

    response = client.get("/api/security/organizations/")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------- POST /api/security/organizations/


@pytest.mark.django_db
def test_post_org_requires_authentication(client):
    response = client.post("/api/security/organizations/", {"name": "New Org"}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_post_org_requires_admin(client, regular_user):
    client.force_login(regular_user)
    response = client.post("/api/security/organizations/", {"name": "New Org"}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_admin_creates_org_and_wazuh_group(mock_wazuh_cls, admin_client):
    mock_client = mock_wazuh_cls.return_value
    mock_client.create_group.return_value = None

    response = admin_client.post(
        "/api/security/organizations/",
        {"name": "New Customer"},
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Customer"
    assert data["slug"] == "new-customer"
    assert data["wazuh_group"] == "new-customer"
    mock_client.create_group.assert_called_once_with("new-customer")
    assert Organization.objects.filter(slug="new-customer").exists()


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_wazuh_failure_rolls_back_org_creation(mock_wazuh_cls, admin_client):
    mock_client = mock_wazuh_cls.return_value
    mock_client.create_group.side_effect = WazuhAPIError("group already exists")

    response = admin_client.post(
        "/api/security/organizations/",
        {"name": "Bad Org"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Wazuh" in response.json()["detail"]
    assert not Organization.objects.filter(slug="bad-org").exists()


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_missing_name_returns_400(mock_wazuh_cls, admin_client):
    response = admin_client.post(
        "/api/security/organizations/",
        {},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "name" in response.json()["detail"]


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_slug_auto_generated_from_name(mock_wazuh_cls, admin_client):
    mock_wazuh_cls.return_value.create_group.return_value = None

    response = admin_client.post(
        "/api/security/organizations/",
        {"name": "My New Customer Inc."},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["slug"] == "my-new-customer-inc"


@pytest.mark.django_db
@patch("security.views.WazuhClient")
def test_slug_collision_appends_number(mock_wazuh_cls, acme, admin_client):
    mock_wazuh_cls.return_value.create_group.return_value = None

    response = admin_client.post(
        "/api/security/organizations/",
        {"name": "Acme"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["slug"] == "acme-2"
