from unittest.mock import patch

import pytest
from security.models import Organization, OrganizationMembership, WorkPackage, WorkPackageItem


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


def _make_package(acme, db):
    pkg = WorkPackage.objects.create(org=acme)
    WorkPackageItem.objects.create(
        work_package=pkg,
        cve_id="CVE-2024-0001",
        severity="critical",
        cvss_score=9.8,
        description="A critical flaw.",
        affected_agent_count=3,
        impact_score=30.0,
    )
    return pkg


def post_generate(client, org_slug="acme"):
    return client.post(f"/api/security/work-package/generate/?org={org_slug}")


# ---------------------------------------------------------------- access control


@pytest.mark.django_db
def test_generate_requires_authentication(client, acme):
    response = post_generate(client)
    assert response.status_code == 403


@pytest.mark.django_db
def test_generate_non_staff_gets_403(client, acme_member, acme):
    client.force_login(acme_member)
    response = post_generate(client)
    assert response.status_code == 403


@pytest.mark.django_db
def test_generate_missing_org_returns_400(admin_client):
    response = admin_client.post("/api/security/work-package/generate/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_generate_unknown_org_returns_404(admin_client):
    response = post_generate(admin_client, org_slug="no-such-org")
    assert response.status_code == 404


# ---------------------------------------------------------------- successful generation


@pytest.mark.django_db
@patch("security.views.generate_work_package")
def test_generate_staff_creates_package(mock_generate, admin_client, acme):
    pkg = _make_package(acme, None)
    mock_generate.return_value = pkg

    response = post_generate(admin_client)

    assert response.status_code == 201
    mock_generate.assert_called_once()
    call_args = mock_generate.call_args
    assert call_args[0][0] == acme


@pytest.mark.django_db
@patch("security.views.generate_work_package")
def test_generate_response_includes_package_and_items(mock_generate, admin_client, acme):
    pkg = _make_package(acme, None)
    mock_generate.return_value = pkg

    response = post_generate(admin_client)

    data = response.json()
    assert data["package"]["id"] == pkg.id
    assert len(data["package"]["items"]) == 1
    assert data["package"]["items"][0]["cve_id"] == "CVE-2024-0001"


@pytest.mark.django_db
@patch("security.views.generate_work_package")
def test_generate_passes_requesting_user(mock_generate, admin_client, acme, django_user_model):
    pkg = _make_package(acme, None)
    mock_generate.return_value = pkg

    post_generate(admin_client)

    call_kwargs = mock_generate.call_args
    # generated_by kwarg should be the admin user (not None)
    assert call_kwargs[1]["generated_by"] is not None


@pytest.mark.django_db
@patch("security.views.generate_work_package")
def test_generate_returns_502_when_service_returns_none(mock_generate, admin_client, acme):
    mock_generate.return_value = None

    response = post_generate(admin_client)

    assert response.status_code == 502
