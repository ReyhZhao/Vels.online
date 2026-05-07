from datetime import datetime, timedelta, timezone as dt_timezone

from celery import shared_task


@shared_task
def cleanup_orphaned_attachments():
    """Remove S3 objects under incidents/ that have no Attachment row and are older than 24h."""
    from security.storage import StorageClient
    from incidents.models import Attachment

    client = StorageClient()
    cutoff = datetime.now(dt_timezone.utc) - timedelta(hours=24)
    existing_keys = set(Attachment.objects.values_list("s3_key", flat=True))

    for obj in client.list_objects("incidents/"):
        if obj["Key"] not in existing_keys and obj["LastModified"] < cutoff:
            client.delete_file(obj["Key"])
