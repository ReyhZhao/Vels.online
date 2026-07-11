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


# ── auditing: last-used time/IP (#696) ────────────────────────────────────────


@pytest.mark.django_db
def test_last_used_recorded_on_authenticated_request(admin_client, client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme])
    auth = f"Token {account.token.key}"

    assert account.last_used_at is None
    resp = client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=auth, HTTP_X_FORWARDED_FOR="203.0.113.7"
    )
    assert resp.status_code == 200

    account.refresh_from_db()
    assert account.last_used_at is not None
    assert account.last_used_ip == "203.0.113.7"

    # Surfaced by the staff management API for auditing.
    row = next(r for r in admin_client.get("/api/security/service-accounts/").json() if r["id"] == account.pk)
    assert row["last_used_ip"] == "203.0.113.7"
    assert row["last_used_at"] is not None


@pytest.mark.django_db
def test_client_ip_taken_from_rightmost_forwarded_for(client, acme):
    """Behind one trusted proxy, the real client is the rightmost XFF entry — the one
    the proxy appended. The leftmost value is caller-supplied and must be ignored."""
    account = ServiceAccount.create(name="svc", orgs=[acme])
    auth = f"Token {account.token.key}"

    resp = client.get(
        "/api/security/organizations/",
        HTTP_AUTHORIZATION=auth,
        HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.7",
    )
    assert resp.status_code == 200
    account.refresh_from_db()
    assert account.last_used_ip == "203.0.113.7"


# ── source-IP allowlist (#696) ────────────────────────────────────────────────


@pytest.mark.django_db
def test_allowlist_permits_matching_ip_and_denies_others(client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme], allowed_ips=["203.0.113.0/24"])
    auth = f"Token {account.token.key}"

    # In range → authenticates.
    assert client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=auth, HTTP_X_FORWARDED_FOR="203.0.113.9"
    ).status_code == 200

    # Out of range → rejected at auth time.
    assert client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=auth, HTTP_X_FORWARDED_FOR="198.51.100.4"
    ).status_code == 401


@pytest.mark.django_db
def test_rejected_attempt_does_not_update_last_used(client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme], allowed_ips=["203.0.113.0/24"])
    auth = f"Token {account.token.key}"

    resp = client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=auth, HTTP_X_FORWARDED_FOR="198.51.100.4"
    )
    assert resp.status_code == 401
    account.refresh_from_db()
    assert account.last_used_at is None
    assert account.last_used_ip is None


@pytest.mark.django_db
def test_spoofed_leftmost_forwarded_for_cannot_bypass_allowlist(client, acme):
    """A caller pre-setting a forged leftmost XFF cannot slip past the allowlist: the
    trusted value is the rightmost (proxy-appended) one."""
    account = ServiceAccount.create(name="svc", orgs=[acme], allowed_ips=["203.0.113.0/24"])
    auth = f"Token {account.token.key}"

    # Caller forges an in-range leftmost value; the proxy appends the real, out-of-range IP.
    assert client.get(
        "/api/security/organizations/",
        HTTP_AUTHORIZATION=auth,
        HTTP_X_FORWARDED_FOR="203.0.113.9, 198.51.100.4",
    ).status_code == 401


@pytest.mark.django_db
def test_empty_allowlist_is_unrestricted(client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme], allowed_ips=[])
    auth = f"Token {account.token.key}"
    assert client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=auth, HTTP_X_FORWARDED_FOR="198.51.100.4"
    ).status_code == 200


@pytest.mark.django_db
def test_allowlist_supports_ipv6(client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme], allowed_ips=["2001:db8::/32"])
    auth = f"Token {account.token.key}"
    assert client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=auth, HTTP_X_FORWARDED_FOR="2001:db8::1"
    ).status_code == 200
    assert client.get(
        "/api/security/organizations/", HTTP_AUTHORIZATION=auth, HTTP_X_FORWARDED_FOR="2001:dead::1"
    ).status_code == 401


# ── managing the allowlist through the API (#696) ─────────────────────────────


@pytest.mark.django_db
def test_create_with_allowlist_normalises_and_persists(admin_client, acme):
    resp = _post(
        admin_client,
        "/api/security/service-accounts/",
        {"name": "svc", "org_slugs": ["acme"], "allowed_ips": ["203.0.113.5/24", "10.0.0.1"]},
    )
    assert resp.status_code == 201
    # Host-bit-set CIDR is normalised to its network address.
    assert resp.json()["allowed_ips"] == ["203.0.113.0/24", "10.0.0.1/32"]


@pytest.mark.django_db
def test_create_rejects_invalid_allowlist_entry(admin_client, acme):
    resp = _post(
        admin_client,
        "/api/security/service-accounts/",
        {"name": "svc", "org_slugs": ["acme"], "allowed_ips": ["not-an-ip"]},
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_patch_updates_allowlist(admin_client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme])
    resp = _patch(
        admin_client,
        f"/api/security/service-accounts/{account.pk}/",
        {"allowed_ips": ["192.0.2.0/24"]},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed_ips"] == ["192.0.2.0/24"]
    account.refresh_from_db()
    assert account.allowed_ips == ["192.0.2.0/24"]


@pytest.mark.django_db
def test_patch_rejects_invalid_allowlist_entry(admin_client, acme):
    account = ServiceAccount.create(name="svc", orgs=[acme])
    resp = _patch(
        admin_client,
        f"/api/security/service-accounts/{account.pk}/",
        {"allowed_ips": ["999.999.999.999"]},
    )
    assert resp.status_code == 400
