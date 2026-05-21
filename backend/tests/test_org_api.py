from unittest.mock import patch

import pytest

from security.models import Organization, OrganizationMembership
from security.wazuh import WazuhAPIError, WazuhAuthError


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
    assert response.status_code == 401


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
    assert response.status_code == 401


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
def test_wazuh_auth_error_returns_400_not_500(mock_wazuh_cls, admin_client):
    """Regression: 401 from Wazuh must return 400 to the client, not 500."""
    mock_client = mock_wazuh_cls.return_value
    mock_client.create_group.side_effect = WazuhAuthError("Wazuh authentication failed: 401 Unauthorized")

    response = admin_client.post(
        "/api/security/organizations/",
        {"name": "Auth Fail Org"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "Wazuh" in response.json()["detail"]
    assert not Organization.objects.filter(slug="auth-fail-org").exists()


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


# ---------------------------------------------------------------- GET /api/security/organizations/<slug>/


@pytest.mark.django_db
def test_org_detail_returns_triage_prompt_context(admin_client, acme):
    acme.triage_prompt_context = "Treat SSH from 10.0.0.1 as low priority."
    acme.save()

    response = admin_client.get(f"/api/security/organizations/{acme.slug}/")

    assert response.status_code == 200
    assert response.json()["triage_prompt_context"] == "Treat SSH from 10.0.0.1 as low priority."


@pytest.mark.django_db
def test_org_detail_null_triage_prompt_context(admin_client, acme):
    response = admin_client.get(f"/api/security/organizations/{acme.slug}/")
    assert response.status_code == 200
    assert response.json()["triage_prompt_context"] is None


@pytest.mark.django_db
def test_org_detail_returns_404_for_unknown_slug(admin_client):
    response = admin_client.get("/api/security/organizations/no-such-org/")
    assert response.status_code == 404


# ---------------------------------------------------------------- PATCH /api/security/organizations/<slug>/


@pytest.mark.django_db
def test_patch_triage_prompt_context_as_staff(admin_client, acme):
    response = admin_client.patch(
        f"/api/security/organizations/{acme.slug}/",
        {"triage_prompt_context": "Healthcare org — escalate all PHI alerts."},
        content_type="application/json",
    )
    assert response.status_code == 200
    acme.refresh_from_db()
    assert acme.triage_prompt_context == "Healthcare org — escalate all PHI alerts."


@pytest.mark.django_db
def test_patch_triage_prompt_context_clears_when_blank(admin_client, acme):
    acme.triage_prompt_context = "existing context"
    acme.save()

    response = admin_client.patch(
        f"/api/security/organizations/{acme.slug}/",
        {"triage_prompt_context": ""},
        content_type="application/json",
    )
    assert response.status_code == 200
    acme.refresh_from_db()
    assert acme.triage_prompt_context == ""


@pytest.mark.django_db
def test_patch_triage_prompt_context_requires_staff(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.patch(
        f"/api/security/organizations/{acme.slug}/",
        {"triage_prompt_context": "not allowed"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_patch_triage_prompt_context_too_long_returns_400(admin_client, acme):
    response = admin_client.patch(
        f"/api/security/organizations/{acme.slug}/",
        {"triage_prompt_context": "x" * 4001},
        content_type="application/json",
    )
    assert response.status_code == 400
