import uuid

from django.utils import timezone

from security.storage import StorageClient

from ..models import Attachment
from .events import record_event


def issue_upload_url(incident, filename, content_type, uploader, is_internal=True):
    key = f"incidents/{incident.id}/{uuid.uuid4()}-{filename}"
    client = StorageClient()
    url = client.generate_presigned_put_url(key, content_type)
    attachment = Attachment.objects.create(
        incident=incident,
        uploader=uploader,
        s3_key=key,
        filename=filename,
        content_type=content_type,
        is_internal=is_internal,
    )
    return attachment, url


def confirm_upload(attachment):
    client = StorageClient()
    head = client.head_object(attachment.s3_key)
    attachment.size_bytes = head.get("ContentLength", 0)
    attachment.confirmed_at = timezone.now()
    attachment.save(update_fields=["size_bytes", "confirmed_at"])
    record_event(
        attachment.incident,
        "attachment_uploaded",
        actor=attachment.uploader,
        payload={
            "attachment_id": attachment.id,
            "filename": attachment.filename,
            "is_internal": attachment.is_internal,
        },
    )
    return attachment


def issue_download_url(attachment, expiry_seconds=300):
    client = StorageClient()
    return client.generate_presigned_url(attachment.s3_key, expiry_seconds=expiry_seconds)


def delete_attachment(attachment, actor):
    client = StorageClient()
    client.delete_file(attachment.s3_key)
    attachment.deleted_at = timezone.now()
    attachment.save(update_fields=["deleted_at"])
    record_event(
        attachment.incident,
        "attachment_deleted",
        actor=actor,
        payload={"attachment_id": attachment.id, "filename": attachment.filename},
    )
