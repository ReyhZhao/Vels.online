from django.conf import settings

from incidents.services.events import record_event
from notifications.email import send_html_email
from .tokens import build_reply_to_address


def _template_for_role(role):
    return {
        "questioned": "contact_questioned",
        "update": "contact_update",
    }.get(role, "contact_notified")


def _email_context(incident, contact_name, body):
    return {
        "contact_name": contact_name,
        "display_id": incident.display_id,
        "title": incident.title,
        "severity": incident.severity,
        "description": incident.description or "",
        "closure_reason": getattr(incident, "closure_reason", "") or "",
        "message": body,
        "frontend_url": getattr(settings, "FRONTEND_URL", "").rstrip("/"),
    }


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

    context = _email_context(incident, contact.name, body)

    kwargs = {}
    if role == "questioned":
        kwargs["reply_to"] = [build_reply_to_address(incident.id, contact.id)]

    send_html_email(_template_for_role(role), context, [contact.email], **kwargs)
    return msg


def send_contact_email_to_address(incident, email, role, body):
    """Ad-hoc outbound to an address with no Contact record (#721).

    Sends the same role-templated email as a Contact recipient would receive, but
    records no ContactMessage (there is no Contact to attach) and cannot thread
    replies. An incident event is emitted so the outreach is auditable.
    """
    record_event(incident, "contact_email_sent", payload={
        "email": email,
        "role": role,
    })
    context = _email_context(incident, email, body)
    send_html_email(_template_for_role(role), context, [email])
