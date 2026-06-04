import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def evaluate_correlation_rules(alert_id: int):
    """Evaluate all enabled correlation rules against the given alert.

    Enqueued on transaction.on_commit after alert creation so it always
    runs against a fully committed alert (including its entities).
    """
    from alerts.models import Alert
    from correlations.services.evaluator import evaluate

    try:
        alert = Alert.objects.select_related("organization").prefetch_related("entities").get(
            id=alert_id
        )
    except Alert.DoesNotExist:
        logger.warning("evaluate_correlation_rules: alert %s not found", alert_id)
        return

    evaluate(alert)
