"""Tests for incident attachment upload/download/delete endpoints and cleanup task."""

import pytest
from unittest.mock import MagicMock, patch
from django.utils import timezone

from incidents.models import Attachment, Incident
from incidents.services.attachments import (
    confirm_upload,
    delete_attachment,
    issue_download_url,
    issue_upload_url,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def org(db):
    from security.models import Organization
    return Organization.objects.create(name="Acme", slug="acme")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pw", is_staff=True)


@pytest.fixture
def member(db, django_user_model, org):
    from security.models import OrganizationMembership
    user = django_user_model.objects.create_user(username="member", password="pw")
    OrganizationMembership.objects.create(user=user, organization=org)
    return user


@pytest.fixture
def outsider(db, django_user_model):
    return django_user_model.objects.create_user(username="outsider", password="pw")


@pytest.fixture
def incident(db, org, staff):
    return Incident.objects.create(
        organization=org,
        display_id="INC-2026-0001",
        title="Test incident",
        tlp="white",
        created_by=staff,
    )


@pytest.fixture
def confirmed_attachment(db, incident, staff):
    return Attachment.objects.create(
        incident=incident,
        uploader=staff,
        s3_key="incidents/1/abc-report.pdf",
        filename="report.pdf",
        size_bytes=1024,
        content_type="application/pdf",
        is_internal=False,
        confirmed_at=timezone.now(),
    )


@pytest.fixture
def internal_attachment(db, incident, staff):
    return Attachment.objects.create(
        incident=incident,
        uploader=staff,
        s3_key="incidents/1/xyz-secret.pdf",
        filename="secret.pdf",
        size_bytes=512,
        content_type="application/pdf",
        is_internal=True,
        confirmed_at=timezone.now(),
    )


def auth(client, user):
    client.force_login(user)
    return client


# ── service unit tests ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_issue_upload_url_creates_attachment(incident, staff):
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.generate_presigned_put_url.return_value = "https://s3.example.com/put"
        attachment, url = issue_upload_url(incident, "report.pdf", "application/pdf", staff)

    assert attachment.pk is not None
    assert attachment.incident == incident
    assert attachment.filename == "report.pdf"
    assert attachment.is_internal is True
    assert attachment.confirmed_at is None
    assert url == "https://s3.example.com/put"
    assert attachment.s3_key.startswith(f"incidents/{incident.id}/")


@pytest.mark.django_db
def test_issue_upload_url_not_internal_flag(incident, staff):
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.generate_presigned_put_url.return_value = "https://s3.example.com/put"
        attachment, _ = issue_upload_url(incident, "pub.pdf", "application/pdf", staff, is_internal=False)
    assert attachment.is_internal is False


@pytest.mark.django_db
def test_confirm_upload_sets_size_and_timestamp(incident, staff):
    attachment = Attachment.objects.create(
        incident=incident, uploader=staff,
        s3_key="incidents/1/test.pdf", filename="test.pdf",
        content_type="application/pdf",
    )
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.head_object.return_value = {"ContentLength": 2048}
        result = confirm_upload(attachment)

    assert result.size_bytes == 2048
    assert result.confirmed_at is not None


@pytest.mark.django_db
def test_confirm_upload_records_event(incident, staff):
    attachment = Attachment.objects.create(
        incident=incident, uploader=staff,
        s3_key="incidents/1/evt.pdf", filename="evt.pdf",
        content_type="application/pdf",
    )
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.head_object.return_value = {"ContentLength": 100}
        confirm_upload(attachment)

    from incidents.models import IncidentEvent
    event = IncidentEvent.objects.get(incident=incident, kind="attachment_uploaded")
    assert event.payload["filename"] == "evt.pdf"


@pytest.mark.django_db
def test_issue_download_url_calls_storage(confirmed_attachment):
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.generate_presigned_url.return_value = "https://s3.example.com/get"
        url = issue_download_url(confirmed_attachment)
    assert url == "https://s3.example.com/get"
    MockClient.return_value.generate_presigned_url.assert_called_once_with(
        confirmed_attachment.s3_key, expiry_seconds=300
    )


@pytest.mark.django_db
def test_delete_attachment_soft_deletes_and_removes_from_s3(confirmed_attachment, staff):
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        delete_attachment(confirmed_attachment, actor=staff)

    confirmed_attachment.refresh_from_db()
    assert confirmed_attachment.deleted_at is not None
    MockClient.return_value.delete_file.assert_called_once_with(confirmed_attachment.s3_key)


@pytest.mark.django_db
def test_delete_attachment_records_event(confirmed_attachment, staff):
    with patch("incidents.services.attachments.StorageClient"):
        delete_attachment(confirmed_attachment, actor=staff)

    from incidents.models import IncidentEvent
    event = IncidentEvent.objects.get(
        incident=confirmed_attachment.incident, kind="attachment_deleted"
    )
    assert event.payload["filename"] == confirmed_attachment.filename


# ── endpoint tests ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_list_attachments_returns_confirmed_public(client, incident, confirmed_attachment, member):
    auth(client, member)
    res = client.get(f"/api/incidents/{incident.id}/attachments/")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["filename"] == "report.pdf"


@pytest.mark.django_db
def test_list_attachments_hides_internal_from_non_staff(client, incident, confirmed_attachment, internal_attachment, member):
    auth(client, member)
    res = client.get(f"/api/incidents/{incident.id}/attachments/")
    assert res.status_code == 200
    filenames = [a["filename"] for a in res.json()]
    assert "report.pdf" in filenames
    assert "secret.pdf" not in filenames


@pytest.mark.django_db
def test_list_attachments_shows_internal_to_staff(client, incident, confirmed_attachment, internal_attachment, staff):
    auth(client, staff)
    res = client.get(f"/api/incidents/{incident.id}/attachments/")
    assert res.status_code == 200
    assert len(res.json()) == 2


@pytest.mark.django_db
def test_list_attachments_hides_unconfirmed(client, incident, staff):
    Attachment.objects.create(
        incident=incident, uploader=staff,
        s3_key="incidents/1/pending.pdf", filename="pending.pdf",
        content_type="application/pdf", is_internal=False,
    )
    auth(client, staff)
    res = client.get(f"/api/incidents/{incident.id}/attachments/")
    assert res.status_code == 200
    assert len(res.json()) == 0


@pytest.mark.django_db
def test_initiate_upload_returns_attachment_and_url(client, incident, member):
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.generate_presigned_put_url.return_value = "https://s3.example.com/put"
        auth(client, member)
        res = client.post(
            f"/api/incidents/{incident.id}/attachments/",
            {"filename": "report.pdf", "content_type": "application/pdf"},
            content_type="application/json",
        )
    assert res.status_code == 201
    data = res.json()
    assert "upload_url" in data
    assert data["upload_url"] == "https://s3.example.com/put"
    assert data["attachment"]["filename"] == "report.pdf"
    assert data["attachment"]["confirmed_at"] is None


@pytest.mark.django_db
def test_initiate_upload_requires_filename(client, incident, member):
    auth(client, member)
    res = client.post(
        f"/api/incidents/{incident.id}/attachments/",
        {"content_type": "application/pdf"},
        content_type="application/json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_initiate_upload_default_is_internal(client, incident, member):
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.generate_presigned_put_url.return_value = "https://put"
        auth(client, member)
        client.post(
            f"/api/incidents/{incident.id}/attachments/",
            {"filename": "f.pdf", "content_type": "application/pdf"},
            content_type="application/json",
        )
    att = Attachment.objects.get(filename="f.pdf")
    assert att.is_internal is True


@pytest.mark.django_db
def test_confirm_upload_marks_confirmed(client, incident, staff):
    att = Attachment.objects.create(
        incident=incident, uploader=staff,
        s3_key="incidents/1/c.pdf", filename="c.pdf",
        content_type="application/pdf",
    )
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.head_object.return_value = {"ContentLength": 500}
        auth(client, staff)
        res = client.post(f"/api/incidents/{incident.id}/attachments/{att.id}/confirm/")
    assert res.status_code == 200
    assert res.json()["confirmed_at"] is not None


@pytest.mark.django_db
def test_confirm_upload_rejects_double_confirm(client, incident, confirmed_attachment, staff):
    auth(client, staff)
    res = client.post(f"/api/incidents/{incident.id}/attachments/{confirmed_attachment.id}/confirm/")
    assert res.status_code == 400


@pytest.mark.django_db
def test_confirm_upload_forbidden_for_non_uploader(client, incident, member, staff):
    att = Attachment.objects.create(
        incident=incident, uploader=staff,
        s3_key="incidents/1/other.pdf", filename="other.pdf",
        content_type="application/pdf",
    )
    auth(client, member)
    res = client.post(f"/api/incidents/{incident.id}/attachments/{att.id}/confirm/")
    assert res.status_code == 403


@pytest.mark.django_db
def test_download_returns_presigned_url(client, incident, confirmed_attachment, member):
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.generate_presigned_url.return_value = "https://s3.example.com/get"
        auth(client, member)
        res = client.get(f"/api/incidents/{incident.id}/attachments/{confirmed_attachment.id}/download/")
    assert res.status_code == 200
    assert res.json()["url"] == "https://s3.example.com/get"


@pytest.mark.django_db
def test_download_internal_forbidden_for_non_staff(client, incident, internal_attachment, member):
    auth(client, member)
    res = client.get(f"/api/incidents/{incident.id}/attachments/{internal_attachment.id}/download/")
    assert res.status_code == 404


@pytest.mark.django_db
def test_download_internal_allowed_for_staff(client, incident, internal_attachment, staff):
    with patch("incidents.services.attachments.StorageClient") as MockClient:
        MockClient.return_value.generate_presigned_url.return_value = "https://s3.example.com/get"
        auth(client, staff)
        res = client.get(f"/api/incidents/{incident.id}/attachments/{internal_attachment.id}/download/")
    assert res.status_code == 200


@pytest.mark.django_db
def test_delete_attachment_staff_only(client, incident, confirmed_attachment, member):
    auth(client, member)
    res = client.delete(f"/api/incidents/{incident.id}/attachments/{confirmed_attachment.id}/")
    assert res.status_code == 403


@pytest.mark.django_db
def test_delete_attachment_soft_deletes(client, incident, confirmed_attachment, staff):
    with patch("incidents.services.attachments.StorageClient"):
        auth(client, staff)
        res = client.delete(f"/api/incidents/{incident.id}/attachments/{confirmed_attachment.id}/")
    assert res.status_code == 204
    confirmed_attachment.refresh_from_db()
    assert confirmed_attachment.deleted_at is not None


@pytest.mark.django_db
def test_delete_attachment_not_in_list_after_deletion(client, incident, confirmed_attachment, staff):
    with patch("incidents.services.attachments.StorageClient"):
        auth(client, staff)
        client.delete(f"/api/incidents/{incident.id}/attachments/{confirmed_attachment.id}/")
        res = client.get(f"/api/incidents/{incident.id}/attachments/")
    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.django_db
def test_outsider_cannot_list_attachments(client, incident, outsider):
    auth(client, outsider)
    res = client.get(f"/api/incidents/{incident.id}/attachments/")
    assert res.status_code == 404


@pytest.mark.django_db
def test_unauthenticated_cannot_list_attachments(client, incident):
    res = client.get(f"/api/incidents/{incident.id}/attachments/")
    assert res.status_code in (401, 403)


# ── cleanup task ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_cleanup_task_deletes_orphaned_objects(incident):
    from datetime import datetime, timedelta, timezone as dt_timezone
    from incidents.tasks import cleanup_orphaned_attachments

    old_time = datetime.now(dt_timezone.utc) - timedelta(hours=25)
    recent_time = datetime.now(dt_timezone.utc) - timedelta(hours=1)

    orphan_key = "incidents/1/orphan.pdf"
    tracked_key = "incidents/1/tracked.pdf"
    recent_key = "incidents/1/recent-orphan.pdf"

    Attachment.objects.create(
        incident=incident, s3_key=tracked_key,
        filename="tracked.pdf", content_type="application/pdf",
    )

    mock_objects = [
        {"Key": orphan_key, "LastModified": old_time},
        {"Key": tracked_key, "LastModified": old_time},
        {"Key": recent_key, "LastModified": recent_time},
    ]

    with patch("security.storage.StorageClient") as MockClient:
        MockClient.return_value.list_objects.return_value = iter(mock_objects)
        MockClient.return_value.delete_file = MagicMock()
        cleanup_orphaned_attachments()

    MockClient.return_value.delete_file.assert_called_once_with(orphan_key)
