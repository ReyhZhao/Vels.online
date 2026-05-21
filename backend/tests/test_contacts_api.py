import pytest
from contacts.models import Contact
from security.models import Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


def make_contact(org, name="Alice Smith", email="alice@example.com"):
    return Contact.objects.create(organisation=org, name=name, email=email)


# ── GET /api/contacts/ ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_requires_auth(client):
    assert client.get("/api/contacts/").status_code == 401


@pytest.mark.django_db
def test_list_returns_own_org_contacts(client, acme_member, acme, contoso):
    own = make_contact(acme, email="own@acme.com")
    other = make_contact(contoso, email="other@contoso.com")
    client.force_login(acme_member)
    data = client.get("/api/contacts/").json()
    ids = [c["id"] for c in data]
    assert own.id in ids
    assert other.id not in ids


@pytest.mark.django_db
def test_list_staff_sees_all(admin_client, acme, contoso):
    c1 = make_contact(acme, email="a@acme.com")
    c2 = make_contact(contoso, email="b@contoso.com")
    data = admin_client.get("/api/contacts/").json()
    ids = [c["id"] for c in data]
    assert c1.id in ids
    assert c2.id in ids


# ── POST /api/contacts/ ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_requires_auth(client, acme):
    resp = client.post("/api/contacts/", {"org": "acme", "name": "X", "email": "x@x.com"}, content_type="application/json")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_create_non_member_forbidden(client, alice, acme):
    client.force_login(alice)
    resp = client.post("/api/contacts/", {"org": "acme", "name": "X", "email": "x@x.com"}, content_type="application/json")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_member_creates_contact(client, acme_member, acme):
    client.force_login(acme_member)
    resp = client.post(
        "/api/contacts/",
        {"org": "acme", "name": "Bob Jones", "email": "bob@acme.com", "job_title": "Analyst", "department": "SOC"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Bob Jones"
    assert data["email"] == "bob@acme.com"
    assert Contact.objects.filter(organisation=acme, email="bob@acme.com").exists()


@pytest.mark.django_db
def test_create_duplicate_email_rejected(client, acme_member, acme):
    make_contact(acme, email="dup@acme.com")
    client.force_login(acme_member)
    resp = client.post("/api/contacts/", {"org": "acme", "name": "X", "email": "dup@acme.com"}, content_type="application/json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_staff_can_create_for_any_org(admin_client, acme):
    resp = admin_client.post(
        "/api/contacts/",
        {"org": "acme", "name": "Staff Contact", "email": "sc@acme.com"},
        content_type="application/json",
    )
    assert resp.status_code == 201


# ── PATCH /api/contacts/<id>/ ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_patch_requires_auth(client, acme):
    c = make_contact(acme)
    assert client.patch(f"/api/contacts/{c.id}/", {}, content_type="application/json").status_code == 401


@pytest.mark.django_db
def test_patch_updates_fields(client, acme_member, acme):
    c = make_contact(acme, email="patch@acme.com")
    client.force_login(acme_member)
    resp = client.patch(f"/api/contacts/{c.id}/", {"job_title": "Manager"}, content_type="application/json")
    assert resp.status_code == 200
    assert resp.json()["job_title"] == "Manager"


@pytest.mark.django_db
def test_patch_other_org_returns_404(client, alice, contoso):
    c = make_contact(contoso)
    client.force_login(alice)
    resp = client.patch(f"/api/contacts/{c.id}/", {"name": "X"}, content_type="application/json")
    assert resp.status_code == 404


# ── DELETE /api/contacts/<id>/ ────────────────────────────────────────────────


@pytest.mark.django_db
def test_delete_requires_auth(client, acme):
    c = make_contact(acme)
    assert client.delete(f"/api/contacts/{c.id}/").status_code == 401


@pytest.mark.django_db
def test_delete_removes_contact(client, acme_member, acme):
    c = make_contact(acme, email="del@acme.com")
    client.force_login(acme_member)
    resp = client.delete(f"/api/contacts/{c.id}/")
    assert resp.status_code == 204
    assert not Contact.objects.filter(pk=c.id).exists()


@pytest.mark.django_db
def test_delete_other_org_returns_404(client, alice, contoso):
    c = make_contact(contoso)
    client.force_login(alice)
    resp = client.delete(f"/api/contacts/{c.id}/")
    assert resp.status_code == 404


# ── GET /api/contacts/<id>/ ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_get_contact_returns_detail(client, acme_member, acme):
    c = make_contact(acme, name="Detail Test", email="det@acme.com")
    client.force_login(acme_member)
    resp = client.get(f"/api/contacts/{c.id}/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Detail Test"


@pytest.mark.django_db
def test_get_contact_other_org_returns_404(client, alice, contoso):
    c = make_contact(contoso)
    client.force_login(alice)
    assert client.get(f"/api/contacts/{c.id}/").status_code == 404
