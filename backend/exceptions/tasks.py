import logging

from celery import shared_task

logger = logging.getLogger(__name__)

_ARGOCD_SYNC_WAIT = 600  # 10 minutes — allow ArgoCD time to push config to Wazuh


@shared_task
def restart_wazuh_manager():
    """Restart the Wazuh manager so freshly synced rules take effect.

    Scheduled with a countdown of _ARGOCD_SYNC_WAIT seconds after each
    exception rule push so ArgoCD has time to complete its sync first.
    """
    from security.wazuh import WazuhAPIError, WazuhAuthError, WazuhClient

    try:
        WazuhClient().restart_manager()
        logger.info("Wazuh manager restart triggered successfully.")
    except (WazuhAuthError, WazuhAPIError) as exc:
        logger.error("Failed to restart Wazuh manager: %s", exc)
        raise
