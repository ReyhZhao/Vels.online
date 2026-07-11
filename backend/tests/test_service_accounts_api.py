"""Service accounts + API tokens (PRD #694).

A service account is a non-human API principal: a dedicated, non-interactive,
non-staff User whose org access is granted solely via OrganizationMembership, so
the existing membership gate scopes its DRF token. Managed by SOC staff only.
"""

import json

import pytest
from rest_framework.authtoken.models import Token

from security.models import Organization, OrganizationMembership, ServiceAccount


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


def _post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def _patch(client, url, payload):
    return client.patch(url, data=json.dumps(payload), content_type="application/json")


# ── creation ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_staff_creates_service_account_and_token_returned_once(admin_client, acme, contoso):
    resp = _post(
        admin_client,
        "/api/security/service-accounts/",
        {"name": "CI pipeline", "description": "for CI", "org_slugs": ["acme", "contoso"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "CI pipeline"
    assert {o["slug"] for o in data["orgs"]} == {"acme", "contoso"}
    # The token is surfaced exactly once, at creation.
    assert data["token"]

    account = ServiceAccount.objects.get(pk=data["id"])
    assert account.user.is_staff is False
    assert account.user.is_superuser is False
    assert account.user.has_usable_password() is False
    assert data["token"] == account.token.key

    # The list endpoint never redisplays the token value.
    listed = admin_client.get("/api/security/service-accounts/").json()
    assert all("token" not in row for row in listed)


@pytest.mark.django_db
def test_create_requires_name(admin_client):
    resp = _post(admin_client, "/api/security/service-accounts/", {"org_slugs": []})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_rejects_unknown_org(admin_client, acme):
    resp = _post(
        admin_client,
        "/api/security/service-accounts/",
        {"name": "x", "org_slugs": ["acme", "nope"]},
    )
    assert resp.status_code == 400


# ── staff-only gating ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_non_staff_cannot_manage_service_accounts(client, regular_user, acme):
    client.force_login(regular_user)
    assert client.get("/api/security/service-accounts/").status_code == 403
    assert _post(
        client, "/api/security/service-accounts/", {"name": "x", "org_slugs": []}
    ).status_code == 403


@pytest.mark.django_db
def test_anonymous_cannot_manage_service_accounts(client):
    assert client.get("/api/security/service-accounts/").status_code == 401


@pytest.mark.django_db
def test_service_account_token_cannot_manage_service_accounts(admin_client, client, acme):
    """A service account is non-staff, so its own token cannot reach management."""
    account = ServiceAccount.create(name="svc", orgs=[acme])
    auth = f"Token {account.token.key}"
    assert client.get("/api/security/service-accounts/", HTTP_AUTHORIZATION=auth).status_code == 403


# ── token scoping via the existing membership gate ────────────────────────────


@pytest.mark.django_db
def test_token_is_scoped_to_granted_orgs(client, acme, contoso):
    account = ServiceAccount.create(name="svc", orgs=[acme])
    auth = f"Token {account.token.key}"

    # Lists only granted orgs (proves membership scoping + non-staff).
    resp = client.get("/api/security/organizations/", HTTP_AUTHORIZATION=auth)
    assert resp.status_code == 200
    assert {o["slug"] for o in resp.json()} == {"acme"}

    # Granted org: passes the org gate.
    assert client.get(
        "/api/dashboard/overview/?org=acme", HTTP_AUTHORIZATION=auth
    ).status_code == 200
    # Non-granted org: 403 from the same gate a human member hits.
    assert client.get(
        "/api/dashboard/overview/?org=contoso", HTTP_AUTHORIZATION=auth
    ).status_code == 403


@pytest.mark.django_db
def test_editing_org_grants_changes_access_without_new_token(admin_client, client, acme, contoso):
    account = ServiceAccount.create(name="svc", orgs=[acme])
    original_key = account.token.key

    resp = _patch(
        admin_client,
        f"/api/security/service-accounts/{account.pk}/",
        {"org_slugs": ["contoso"]},
    )
    assert resp.status_code == 200
    assert {o["slug"] for o in resp.json()["orgs"]} == {"contoso"}

    # Same token, new scope.
    account.refresh_from_db()
    assert account.token.key == original_key
    auth = f"Token {original_key}"
    assert client.get(
        "/api/dashboard/overview/?org=contoso", HTTP_AUTHORIZATION=auth
    ).status_code == 200
    assert client.get(
        "/api/dashboard/overview/?org=acme", HTTP_AUTHORIZATION=auth
    ).status_code == 403
    # Membership to acme was actually removed.
    assert not OrganizationMembership.objects.filter(
        user=account.user, organization=acme
    ).exists()


# ── token rotation & revocation ───────────────────────────────────────────────


@pytest.mark.django_db
def test_rotate_token_invalidates_old_and_returns_new_once(admin_client, client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme])
    old_key = account.token.key

    resp = admin_client.post(f"/api/security/service-accounts/{account.pk}/rotate-token/")
    assert resp.status_code == 200
    new_key = resp.json()["token"]
    assert new_key != old_key

    # Old token no longer authenticates; new token does.
    assert client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=f"Token {old_key}"
    ).status_code == 401
    assert client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=f"Token {new_key}"
    ).status_code == 200


@pytest.mark.django_db
def test_revoke_deletes_account_user_and_token(admin_client, client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme])
    key = account.token.key
    user_id = account.user_id

    resp = admin_client.delete(f"/api/security/service-accounts/{account.pk}/")
    assert resp.status_code == 204

    assert not ServiceAccount.objects.filter(pk=account.pk).exists()
    assert not Token.objects.filter(key=key).exists()
    # Backing user is gone, so the token cannot authenticate.
    assert client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=f"Token {key}"
    ).status_code == 401


# ── exclusion from human-facing surfaces ──────────────────────────────────────


@pytest.mark.django_db
def test_service_account_absent_from_staff_user_picker(admin_client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme])
    resp = admin_client.get("/api/incidents/staff-users/")
    assert resp.status_code == 200
    usernames = [u.get("username") for u in resp.json()]
    assert account.user.username not in usernames
