import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="inbound_mail.tasks.poll_inbound_mail")
def poll_inbound_mail():
    from .adapters import ImapAdapter
    from .router import route_inbound_message

    adapter = ImapAdapter()
    count = 0
    for message in adapter.fetch_unseen():
        try:
            route_inbound_message(message)
            count += 1
        except Exception:
            logger.exception("inbound_mail: error routing message from %r", message.from_address)
    logger.info("inbound_mail: processed %d message(s)", count)
