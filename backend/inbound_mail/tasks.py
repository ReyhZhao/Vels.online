import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="inbound_mail.tasks.poll_inbound_mail")
def poll_inbound_mail():
    from .adapters import ImapAdapter
    from .router import route_inbound_message

    adapter = ImapAdapter()
    stats = {
        "fetched": 0,
        "contact_reply": 0,
        "phishing_created": 0,
        "phishing_dedup": 0,
        "phishing_dropped": 0,
        "dropped": 0,
        "errors": 0,
    }

    for message in adapter.fetch_unseen():
        stats["fetched"] += 1
        try:
            outcome = route_inbound_message(message)
            _increment(stats, outcome)
        except Exception:
            stats["errors"] += 1
            logger.exception(
                "inbound_mail: unhandled error routing message from=%r subject=%r",
                message.from_address,
                message.subject,
            )

    if stats["fetched"] == 0:
        logger.debug("inbound_mail: poll complete — mailbox empty")
    else:
        logger.info(
            "inbound_mail: poll complete — fetched=%d contact_reply=%d "
            "phishing_created=%d phishing_dedup=%d phishing_dropped=%d dropped=%d errors=%d",
            stats["fetched"],
            stats["contact_reply"],
            stats["phishing_created"],
            stats["phishing_dedup"],
            stats["phishing_dropped"],
            stats["dropped"],
            stats["errors"],
        )

    return stats


def _increment(stats, outcome):
    if outcome == "contact_reply":
        stats["contact_reply"] += 1
    elif outcome == "phishing:created":
        stats["phishing_created"] += 1
    elif outcome == "phishing:dedup":
        stats["phishing_dedup"] += 1
    elif outcome and outcome.startswith("phishing:dropped"):
        stats["phishing_dropped"] += 1
    else:
        stats["dropped"] += 1
