from django.conf import settings

from notifications.email import send_html_email
from .tokens import build_reply_to_address


def send_contact_message(incident, contact, role, body):
    from .models import ContactMessage

    msg = ContactMessage.objects.create(
        incident=incident,
        contact=contact,
        direction=ContactMessage.DIRECTION_OUTBOUND,
        role=role,
        body=body,
    )

    template = "contact_questioned" if role == "questioned" else "contact_notified"
    context = {
        "contact_name": contact.name,
        "display_id": incident.display_id,
        "title": incident.title,
        "severity": incident.severity,
        "message": body,
        "frontend_url": getattr(settings, "FRONTEND_URL", "").rstrip("/"),
    }

    kwargs = {}
    if role == "questioned":
        kwargs["reply_to"] = [build_reply_to_address(incident.id, contact.id)]

    send_html_email(template, context, [contact.email], **kwargs)
    return msg
