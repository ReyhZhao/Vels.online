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


def issue_download_url(attachment, expiry_seconds=300, inline=False):
    client = StorageClient()
    if inline:
        # Serve the object inline (rendered in-browser) rather than as a forced
        # download, so it can be previewed in an iframe/<img>. The stored
        # content_type is echoed back so the browser picks the right renderer.
        safe_name = attachment.filename.replace('"', "")
        return client.generate_presigned_url(
            attachment.s3_key,
            expiry_seconds=expiry_seconds,
            response_content_type=attachment.content_type,
            response_content_disposition=f'inline; filename="{safe_name}"',
        )
    return client.generate_presigned_url(attachment.s3_key, expiry_seconds=expiry_seconds)


def parse_email_attachment(attachment):
    """Parse a stored .eml attachment into a preview-safe structure.

    Reuses the inbound-mail MIME extraction helpers rather than a second parser.
    Returns headers, the text and HTML bodies, and a metadata-only listing of the
    email's own inner attachments (never their bytes). The HTML body is returned
    verbatim; the frontend is responsible for rendering it in a sandboxed,
    remote-load-blocked iframe (phishing safety).
    """
    import email as email_lib

    from inbound_mail.adapters import _extract_attachments, _extract_body

    client = StorageClient()
    raw = client.get_bytes(attachment.s3_key)
    msg = email_lib.message_from_bytes(raw)
    text_body, html_body = _extract_body(msg)
    inner = [
        {"filename": a.filename, "content_type": a.content_type, "size_bytes": len(a.payload)}
        for a in _extract_attachments(msg)
    ]
    headers = {
        "from": msg.get("From", ""),
        "to": msg.get("To", ""),
        "cc": msg.get("Cc", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
    }
    return {
        "headers": headers,
        "text_body": text_body,
        "html_body": html_body,
        "inner_attachments": inner,
    }


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
