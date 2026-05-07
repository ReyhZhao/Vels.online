from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from security.models import Download, Organization, OrganizationMembership


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def acme_member(regular_user, acme):
    OrganizationMembership.objects.create(user=regular_user, organization=acme)
    return regular_user


@pytest.fixture
def global_download(db):
    return Download.objects.create(label="Wazuh Agent (Linux)", platform="linux", category="agent")


@pytest.fixture
def acme_download(acme):
    return Download.objects.create(
        label="Acme Config", platform="all", category="config", organization=acme
    )


@pytest.fixture
def contoso_download(contoso):
    return Download.objects.create(
        label="Contoso Tool", platform="windows", category="tool", organization=contoso
    )


# ---------------------------------------------------------------- GET /api/security/downloads/


@pytest.mark.django_db
def test_downloads_requires_authentication(client, acme):
    response = client.get("/api/security/downloads/?org=acme")
    assert response.status_code == 401


@pytest.mark.django_db
def test_downloads_non_member_gets_403(client, regular_user, acme):
    client.force_login(regular_user)
    response = client.get("/api/security/downloads/?org=acme")
    assert response.status_code == 403


@pytest.mark.django_db
def test_downloads_missing_org_non_admin_gets_400(client, acme_member):
    client.force_login(acme_member)
    response = client.get("/api/security/downloads/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_downloads_includes_global(client, acme_member, global_download, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/downloads/?org=acme")
    assert response.status_code == 200
    ids = [d["id"] for d in response.json()]
    assert global_download.id in ids


@pytest.mark.django_db
def test_downloads_includes_org_specific(client, acme_member, acme_download, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/downloads/?org=acme")
    assert response.status_code == 200
    ids = [d["id"] for d in response.json()]
    assert acme_download.id in ids


@pytest.mark.django_db
def test_downloads_excludes_other_org(client, acme_member, contoso_download, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/downloads/?org=acme")
    assert response.status_code == 200
    ids = [d["id"] for d in response.json()]
    assert contoso_download.id not in ids


@pytest.mark.django_db
def test_downloads_admin_sees_all_without_org(admin_client, global_download, acme_download, contoso_download):
    response = admin_client.get("/api/security/downloads/")
    assert response.status_code == 200
    ids = [d["id"] for d in response.json()]
    assert global_download.id in ids
    assert acme_download.id in ids
    assert contoso_download.id in ids


@pytest.mark.django_db
def test_downloads_serialised_correctly(client, acme_member, global_download, acme):
    client.force_login(acme_member)
    response = client.get("/api/security/downloads/?org=acme")
    assert response.status_code == 200
    item = next(d for d in response.json() if d["id"] == global_download.id)
    assert item["label"] == "Wazuh Agent (Linux)"
    assert item["platform"] == "linux"
    assert item["category"] == "agent"
    assert item["organization_slug"] is None
    assert item["has_file"] is False


# ---------------------------------------------------------------- POST /api/security/downloads/


@pytest.mark.django_db
def test_create_download_requires_authentication(client):
    response = client.post("/api/security/downloads/", {"label": "Test"}, content_type="application/json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_create_download_non_admin_gets_403(client, regular_user):
    client.force_login(regular_user)
    response = client.post("/api/security/downloads/", {"label": "Test"}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_creates_global_download(admin_client):
    response = admin_client.post(
        "/api/security/downloads/",
        {"label": "Sysmon", "platform": "windows", "category": "tool"},
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "Sysmon"
    assert data["platform"] == "windows"
    assert data["category"] == "tool"
    assert data["organization_slug"] is None
    assert data["has_file"] is False


@pytest.mark.django_db
def test_admin_creates_org_specific_download(admin_client, acme):
    response = admin_client.post(
        "/api/security/downloads/",
        {"label": "Acme Config", "platform": "all", "category": "config", "organization_slug": "acme"},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["organization_slug"] == "acme"


@pytest.mark.django_db
def test_create_download_unknown_org_returns_404(admin_client):
    response = admin_client.post(
        "/api/security/downloads/",
        {"label": "X", "platform": "all", "category": "agent", "organization_slug": "no-such-org"},
        content_type="application/json",
    )
    assert response.status_code == 404


# ---------------------------------------------------------------- GET /api/security/downloads/<id>/presigned/


@pytest.mark.django_db
def test_presigned_requires_authentication(client, global_download):
    response = client.get(f"/api/security/downloads/{global_download.id}/presigned/")
    assert response.status_code == 401


@pytest.mark.django_db
@patch("security.views.StorageClient")
def test_presigned_returns_url_for_global_download(mock_storage_cls, client, acme_member, global_download):
    global_download.s3_key = "downloads/1/agent.deb"
    global_download.save()
    mock_storage_cls.return_value.generate_presigned_url.return_value = "https://s3.example.com/signed"

    client.force_login(acme_member)
    response = client.get(f"/api/security/downloads/{global_download.id}/presigned/")

    assert response.status_code == 200
    assert response.json()["url"] == "https://s3.example.com/signed"
    mock_storage_cls.return_value.generate_presigned_url.assert_called_once_with(
        "downloads/1/agent.deb", expiry_seconds=300
    )


@pytest.mark.django_db
@patch("security.views.StorageClient")
def test_presigned_org_download_requires_membership(mock_storage_cls, client, regular_user, acme_download):
    acme_download.s3_key = "downloads/2/config.zip"
    acme_download.save()
    client.force_login(regular_user)
    response = client.get(f"/api/security/downloads/{acme_download.id}/presigned/")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.StorageClient")
def test_presigned_org_download_accessible_to_member(mock_storage_cls, client, acme_member, acme_download):
    acme_download.s3_key = "downloads/2/config.zip"
    acme_download.save()
    mock_storage_cls.return_value.generate_presigned_url.return_value = "https://s3.example.com/signed"
    client.force_login(acme_member)
    response = client.get(f"/api/security/downloads/{acme_download.id}/presigned/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_presigned_no_file_returns_404(client, acme_member, global_download):
    client.force_login(acme_member)
    response = client.get(f"/api/security/downloads/{global_download.id}/presigned/")
    assert response.status_code == 404


# ---------------------------------------------------------------- POST /api/security/downloads/<id>/upload/


@pytest.mark.django_db
def test_upload_requires_authentication(client, global_download):
    response = client.post(f"/api/security/downloads/{global_download.id}/upload/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_upload_non_admin_gets_403(client, regular_user, global_download):
    client.force_login(regular_user)
    response = client.post(f"/api/security/downloads/{global_download.id}/upload/")
    assert response.status_code == 403


@pytest.mark.django_db
@patch("security.views.StorageClient")
def test_admin_upload_streams_to_wasabi(mock_storage_cls, admin_client, global_download):
    upload = SimpleUploadedFile("agent.deb", b"fake binary content", content_type="application/octet-stream")
    response = admin_client.post(
        f"/api/security/downloads/{global_download.id}/upload/",
        {"file": upload},
    )
    assert response.status_code == 200
    mock_storage_cls.return_value.upload_file.assert_called_once()
    call_args = mock_storage_cls.return_value.upload_file.call_args
    assert call_args[0][1] == f"downloads/{global_download.id}/agent.deb"


@pytest.mark.django_db
@patch("security.views.StorageClient")
def test_upload_stores_s3_key(mock_storage_cls, admin_client, global_download):
    upload = SimpleUploadedFile("tool.exe", b"data", content_type="application/octet-stream")
    admin_client.post(
        f"/api/security/downloads/{global_download.id}/upload/",
        {"file": upload},
    )
    global_download.refresh_from_db()
    assert global_download.s3_key == f"downloads/{global_download.id}/tool.exe"
    assert global_download.s3_key != ""


@pytest.mark.django_db
def test_upload_missing_file_returns_400(admin_client, global_download):
    response = admin_client.post(
        f"/api/security/downloads/{global_download.id}/upload/",
        {},
        content_type="application/json",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------- DELETE /api/security/downloads/<id>/


@pytest.mark.django_db
def test_delete_requires_authentication(client, global_download):
    response = client.delete(f"/api/security/downloads/{global_download.id}/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_delete_non_admin_gets_403(client, regular_user, global_download):
    client.force_login(regular_user)
    response = client.delete(f"/api/security/downloads/{global_download.id}/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_deletes_download(admin_client, global_download):
    response = admin_client.delete(f"/api/security/downloads/{global_download.id}/")
    assert response.status_code == 204
    assert not Download.objects.filter(pk=global_download.id).exists()


@pytest.mark.django_db
def test_delete_nonexistent_returns_404(admin_client):
    response = admin_client.delete("/api/security/downloads/99999/")
    assert response.status_code == 404


@pytest.mark.django_db
@patch("security.views.StorageClient")
def test_delete_removes_s3_file_when_present(mock_storage_cls, admin_client, global_download):
    global_download.s3_key = "downloads/1/agent.deb"
    global_download.save()
    response = admin_client.delete(f"/api/security/downloads/{global_download.id}/")
    assert response.status_code == 204
    mock_storage_cls.return_value.delete_file.assert_called_once_with("downloads/1/agent.deb")


@pytest.mark.django_db
@patch("security.views.StorageClient")
def test_delete_no_s3_call_when_no_file(mock_storage_cls, admin_client, global_download):
    response = admin_client.delete(f"/api/security/downloads/{global_download.id}/")
    assert response.status_code == 204
    mock_storage_cls.return_value.delete_file.assert_not_called()
