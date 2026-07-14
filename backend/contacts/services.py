from django.conf import settings

from incidents.services.events import record_event
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

    record_event(incident, "contact_message_sent", payload={
        "contact_id": contact.id,
        "contact_name": contact.name,
        "role": role,
    })

    template = {
        "questioned": "contact_questioned",
        "update": "contact_update",
    }.get(role, "contact_notified")
    context = {
        "contact_name": contact.name,
        "display_id": incident.display_id,
        "title": incident.title,
        "severity": incident.severity,
        "description": incident.description or "",
        "closure_reason": getattr(incident, "closure_reason", "") or "",
        "message": body,
        "frontend_url": getattr(settings, "FRONTEND_URL", "").rstrip("/"),
    }

    kwargs = {}
    if role == "questioned":
        kwargs["reply_to"] = [build_reply_to_address(incident.id, contact.id)]

    send_html_email(template, context, [contact.email], **kwargs)
    return msg
