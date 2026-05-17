from unittest.mock import MagicMock, patch

import pytest

from security.models import OrgInvitation, Organization, OrganizationMembership
from signups.authentik import AuthentikAPIError


@pytest.fixture(autouse=True)
def authentik_settings(settings):
    settings.AUTHENTIK_API_URL = "https://auth.example.com"
    settings.AUTHENTIK_API_TOKEN = "test-token"
    settings.AUTHENTIK_ENROLLMENT_FLOW_SLUG = "enrollment"
    settings.FRONTEND_URL = "https://app.example.com"


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


_FAKE_TOKEN = "12345678-1234-5678-1234-567812345678"


def _mock_client(group_pk="grp-uuid", flow_uuid="flow-uuid", invite_token=_FAKE_TOKEN):
    client = MagicMock()
    client.find_group_by_name.return_value = group_pk
    client.create_group.return_value = group_pk
    client.get_flow_uuid.return_value = flow_uuid
    client.create_invitation.return_value = {"pk": invite_token, "token": invite_token}
    return client


# ── GET /api/security/organizations/<slug>/invite/ ────────────────────────────


@pytest.mark.django_db
def test_list_invitations_requires_staff(client, acme, django_user_model):
    user = django_user_model.objects.create_user(username="bob", password="pass")
    client.force_login(user)
    resp = client.get(f"/api/security/organizations/{acme.slug}/invite/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_list_invitations_empty(client, acme, staff):
    client.force_login(staff)
    resp = client.get(f"/api/security/organizations/{acme.slug}/invite/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.django_db
def test_list_invitations_returns_existing(client, acme, staff):
    OrgInvitation.objects.create(
        organization=acme,
        email="alice@example.com",
        full_name="Alice",
        role=OrgInvitation.ROLE_STAFF,
        invited_by=staff,
    )
    client.force_login(staff)
    resp = client.get(f"/api/security/organizations/{acme.slug}/invite/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["email"] == "alice@example.com"
    assert data[0]["role"] == "staff"


# ── POST /api/security/organizations/<slug>/invite/ ───────────────────────────


@pytest.mark.django_db
def test_create_invite_requires_staff(client, acme, django_user_model):
    user = django_user_model.objects.create_user(username="bob", password="pass")
    client.force_login(user)
    resp = client.post(
        f"/api/security/organizations/{acme.slug}/invite/",
        {"email": "x@x.com", "full_name": "X"},
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_invite_404_for_unknown_org(client, staff):
    client.force_login(staff)
    resp = client.post(
        "/api/security/organizations/nope/invite/",
        {"email": "x@x.com", "full_name": "X"},
        content_type="application/json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_create_invite_validates_required_fields(client, acme, staff):
    client.force_login(staff)
    resp = client.post(
        f"/api/security/organizations/{acme.slug}/invite/",
        {"full_name": "No Email"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "email" in resp.json()["detail"]


@pytest.mark.django_db
def test_create_invite_validates_role(client, acme, staff):
    client.force_login(staff)
    resp = client.post(
        f"/api/security/organizations/{acme.slug}/invite/",
        {"email": "x@x.com", "full_name": "X", "role": "superadmin"},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_invite_creates_record_and_sends_email(client, acme, staff):
    mock_client = _mock_client()
    with (
        patch("security.views.AuthentikClient", return_value=mock_client),
        patch("security.tasks.send_org_invite_email.delay") as mock_delay,
    ):
        client.force_login(staff)
        resp = client.post(
            f"/api/security/organizations/{acme.slug}/invite/",
            {"email": "alice@example.com", "full_name": "Alice", "role": "staff"},
            content_type="application/json",
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert data["role"] == "staff"
    assert data["status"] == "pending"

    inv = OrgInvitation.objects.get(email="alice@example.com")
    assert inv.organization == acme
    assert inv.role == OrgInvitation.ROLE_STAFF
    assert inv.invited_by == staff
    mock_delay.assert_called_once_with(inv.pk)


@pytest.mark.django_db
def test_create_invite_uses_existing_authentik_group(client, acme, staff):
    mock_client = _mock_client(group_pk="existing-grp")
    with (
        patch("security.views.AuthentikClient", return_value=mock_client),
        patch("security.tasks.send_org_invite_email.delay"),
    ):
        client.force_login(staff)
        client.post(
            f"/api/security/organizations/{acme.slug}/invite/",
            {"email": "b@b.com", "full_name": "B"},
            content_type="application/json",
        )

    mock_client.find_group_by_name.assert_called_once_with("customer:acme")
    mock_client.create_group.assert_not_called()


@pytest.mark.django_db
def test_create_invite_creates_group_when_missing(client, acme, staff):
    mock_client = _mock_client()
    mock_client.find_group_by_name.return_value = None
    with (
        patch("security.views.AuthentikClient", return_value=mock_client),
        patch("security.tasks.send_org_invite_email.delay"),
    ):
        client.force_login(staff)
        client.post(
            f"/api/security/organizations/{acme.slug}/invite/",
            {"email": "c@c.com", "full_name": "C"},
            content_type="application/json",
        )

    mock_client.create_group.assert_called_once_with("customer:acme")


@pytest.mark.django_db
def test_create_invite_returns_502_on_authentik_error(client, acme, staff):
    mock_client = MagicMock()
    mock_client.find_group_by_name.side_effect = AuthentikAPIError(500, "boom")
    with patch("signups.authentik.AuthentikClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.post(
            f"/api/security/organizations/{acme.slug}/invite/",
            {"email": "d@d.com", "full_name": "D"},
            content_type="application/json",
        )
    assert resp.status_code == 502


# ── signals: apply grants on first login ─────────────────────────────────────


@pytest.mark.django_db
def test_signal_applies_staff_grant_on_first_login(db, acme, django_user_model):
    from security.signals import sync_org_memberships

    OrgInvitation.objects.create(
        organization=acme,
        email="new@example.com",
        full_name="New User",
        role=OrgInvitation.ROLE_STAFF,
    )

    user = django_user_model.objects.create_user(
        username="newuser", password="pass", email="new@example.com"
    )
    assert not user.is_staff

    sync_org_memberships(user, [f"customer:{acme.slug}"])

    user.refresh_from_db()
    assert user.is_staff
    assert OrgInvitation.objects.get(email="new@example.com").status == OrgInvitation.STATUS_ACCEPTED


@pytest.mark.django_db
def test_signal_applies_admin_grant_on_first_login(db, acme, django_user_model):
    from security.signals import sync_org_memberships

    OrgInvitation.objects.create(
        organization=acme,
        email="admin@example.com",
        full_name="Admin User",
        role=OrgInvitation.ROLE_ADMIN,
    )

    user = django_user_model.objects.create_user(
        username="adminuser", password="pass", email="admin@example.com"
    )
    sync_org_memberships(user, [f"customer:{acme.slug}"])

    user.refresh_from_db()
    assert user.is_staff
    assert user.is_superuser


@pytest.mark.django_db
def test_signal_no_grant_for_member_role(db, acme, django_user_model):
    from security.signals import sync_org_memberships

    OrgInvitation.objects.create(
        organization=acme,
        email="member@example.com",
        full_name="Member",
        role=OrgInvitation.ROLE_MEMBER,
    )

    user = django_user_model.objects.create_user(
        username="memberuser", password="pass", email="member@example.com"
    )
    sync_org_memberships(user, [f"customer:{acme.slug}"])

    user.refresh_from_db()
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.django_db
def test_signal_skips_grant_if_no_invitation(db, acme, django_user_model):
    from security.signals import sync_org_memberships

    user = django_user_model.objects.create_user(
        username="noninvited", password="pass", email="other@example.com"
    )
    sync_org_memberships(user, [f"customer:{acme.slug}"])

    user.refresh_from_db()
    assert not user.is_staff


# ── AuthentikClient.find_group_by_name ────────────────────────────────────────


@pytest.mark.django_db
def test_find_group_by_name_returns_pk():
    from unittest.mock import MagicMock, patch
    from signups.authentik import AuthentikClient

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"results": [{"pk": "grp-abc", "name": "customer:acme"}]}

    with patch("signups.authentik.requests.get", return_value=mock_resp):
        pk = AuthentikClient().find_group_by_name("customer:acme")

    assert pk == "grp-abc"


@pytest.mark.django_db
def test_find_group_by_name_returns_none_when_missing():
    from unittest.mock import MagicMock, patch
    from signups.authentik import AuthentikClient

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"results": []}

    with patch("signups.authentik.requests.get", return_value=mock_resp):
        pk = AuthentikClient().find_group_by_name("customer:nope")

    assert pk is None
