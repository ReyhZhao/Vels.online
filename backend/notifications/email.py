import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Template
from django.template.context import Context


def _strip_html(html):
    """Plain-text fallback: strips style/script blocks then HTML tags."""
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    text = re.sub(r"\s{2,}", "\n", text)
    return text.strip()


def _render_string(template_string, context_dict):
    """Render a Django template string bypassing test-client signal instrumentation.

    Django 5.0's Context.__copy__ is broken on Python 3.14; calling
    Template.render() fires the template_rendered signal which causes the
    test client to copy() the context and crash. Using nodelist.render()
    directly avoids the signal.
    """
    template = Template(template_string)
    ctx = Context(context_dict)
    return template.nodelist.render(ctx)


def render_template_string(template_string, context):
    """Render an arbitrary Django template string against a context dict.

    Public wrapper over the signal-free renderer, for callers (e.g. contact-task
    bodies) that store their own template text rather than a named EmailTemplate.
    """
    return _render_string(template_string or "", context)


def render_email(template_name, context):
    """Return (subject, html_body, plain_body) for the named template.

    Falls back to the built-in defaults when no DB override exists.
    """
    from .models import EmailTemplate
    from .email_defaults import DEFAULT_TEMPLATES

    try:
        tmpl = EmailTemplate.objects.get(name=template_name)
        subject_tpl = tmpl.subject
        html_tpl = tmpl.html_body
    except EmailTemplate.DoesNotExist:
        defaults = DEFAULT_TEMPLATES.get(template_name, {})
        subject_tpl = defaults.get("subject", template_name)
        html_tpl = defaults.get("html_body", "")

    subject = _render_string(subject_tpl, context)
    html = _render_string(html_tpl, context)
    plain = _strip_html(html)
    return subject, html, plain


def send_html_email(template_name, context, recipient_list, from_email=None, reply_to=None):
    """Render and send an HTML email with a plain-text fallback."""
    subject, html, plain = render_email(template_name, context)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=plain,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
        reply_to=reply_to or [],
    )
    msg.attach_alternative(html, "text/html")
    msg.send()
