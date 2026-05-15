from celery import shared_task
from django.utils import timezone
from datetime import timedelta


@shared_task
def cleanup_old_task_results():
    from django_celery_results.models import TaskResult
    cutoff = timezone.now() - timedelta(days=90)
    deleted, _ = TaskResult.objects.filter(date_done__lt=cutoff).delete()
    return {"deleted": deleted}
