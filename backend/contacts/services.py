from django.utils import timezone

from notifications.email import send_html_email
from .tokens import build_reply_to_address


def send_contact_email(incident_contact):
    """Send a notified or questioned email to the linked contact and stamp sent_at."""
    contact = incident_contact.contact
    incident = incident_contact.incident
    role = incident_contact.role

    template = "contact_questioned" if role == "questioned" else "contact_notified"

    context = {
        "contact_name": contact.name,
        "display_id": incident.display_id,
        "title": incident.title,
        "severity": incident.severity,
        "message": incident_contact.message,
    }

    kwargs = {}
    if role == "questioned":
        kwargs["reply_to"] = [build_reply_to_address(incident.id, contact.id)]

    send_html_email(template, context, [contact.email], **kwargs)

    incident_contact.sent_at = timezone.now()
    incident_contact.save(update_fields=["sent_at"])
