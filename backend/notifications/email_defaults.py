"""
Default HTML email templates. Used as fallbacks when no EmailTemplate row
exists for that name. Full HTML documents using Django template syntax:
{{ var }}, {% for %}, {% if %}, etc.
"""

_STYLES = (
    "body{margin:0;padding:0;background:#0a1020;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased;}"
    "a{color:#3b82f6;}"
    "h1{font-size:22px;font-weight:600;margin:0 0 8px;color:#f0f4ff;}"
    "p{margin:0 0 16px;font-size:15px;line-height:1.6;color:#94a3b8;}"
    ".btn{display:inline-block;background:#3b82f6;color:#0a1020 !important;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:600;font-size:14px;}"
    ".divider{border:none;border-top:1px solid #1e2d4f;margin:24px 0;}"
    ".badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:500;text-transform:uppercase;letter-spacing:.04em;}"
    ".badge-critical{background:rgba(239,68,68,.15);color:#f87171;}"
    ".badge-high{background:rgba(249,115,22,.15);color:#fb923c;}"
    ".badge-medium{background:rgba(234,179,8,.15);color:#facc15;}"
    ".badge-low{background:rgba(59,130,246,.15);color:#60a5fa;}"
    ".badge-info{background:rgba(107,114,128,.15);color:#9ca3af;}"
    ".incident-card{background:#0d1829;border:1px solid #1e2d4f;border-radius:6px;padding:16px;margin-bottom:12px;}"
    ".incident-id{font-family:monospace;font-size:12px;color:#3b82f6;font-weight:600;}"
    ".incident-title{font-size:15px;color:#f0f4ff;font-weight:500;margin:4px 0 8px;}"
    ".meta{font-size:12px;color:#64748b;}"
    ".notif-item{padding:12px 0;border-bottom:1px solid #1e2d4f;}"
    ".notif-item:last-child{border-bottom:none;}"
    ".notif-title{font-size:14px;font-weight:500;color:#f0f4ff;margin-bottom:4px;}"
    ".notif-body{font-size:13px;color:#94a3b8;}"
    ".event-row{padding:8px 0;font-size:13px;color:#64748b;border-bottom:1px solid #1e2d4f;}"
    ".event-row:last-child{border-bottom:none;}"
)

# _FOOTER uses {{ frontend_url }} — a Django template variable rendered at send time.
_FOOTER = (
    "<td style=\"padding-top:20px;text-align:center;font-size:12px;color:#475569;line-height:1.5;\">"
    "&copy; vels.online &mdash; "
    "<a href=\"{{ frontend_url }}\" style=\"color:#3b82f6;text-decoration:none;\">Open dashboard</a>"
    "</td>"
)


def _base(title, content):
    """Wrap email content in the shared HTML shell."""
    return (
        "<!DOCTYPE html>"
        "<html lang=\"en\">"
        "<head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{title}</title>"
        f"<style>{_STYLES}</style>"
        "</head>"
        "<body>"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\">"
        "<tr><td align=\"center\" style=\"padding:40px 16px;\">"
        "<table width=\"600\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" style=\"max-width:600px;width:100%;\">"
        # Logo row
        "<tr><td style=\"padding-bottom:20px;\">"
        "<span style=\"font-size:22px;font-weight:700;color:#3b82f6;\">vels"
        "<span style=\"color:#f0f4ff;\">.online</span></span>"
        "</td></tr>"
        # Card row
        "<tr><td style=\"background:#111d35;border:1px solid #1e2d4f;border-radius:8px;padding:32px;\">"
        + content +
        "</td></tr>"
        # Footer row
        f"<tr>{_FOOTER}</tr>"
        "</table>"
        "</td></tr>"
        "</table>"
        "</body>"
        "</html>"
    )


# ---------------------------------------------------------------------------
# notification_digest
# Context: recipient_name, count, items[{title,body,link}], frontend_url
# ---------------------------------------------------------------------------
_NOTIF_DIGEST_BODY = (
    "<h1>{{ count }} notification{{ count|pluralize }}</h1>"
    "<p>Hi {{ recipient_name }}, here is a summary of your recent notifications.</p>"
    "<hr class=\"divider\">"
    "{% for item in items %}"
    "<div class=\"notif-item\">"
    "<div class=\"notif-title\">{{ item.title }}</div>"
    "{% if item.body %}<div class=\"notif-body\">{{ item.body }}</div>{% endif %}"
    "{% if item.link %}<div style=\"margin-top:6px;\"><a href=\"{{ item.link }}\">View &rarr;</a></div>{% endif %}"
    "</div>"
    "{% endfor %}"
    "<hr class=\"divider\">"
    "<p><a href=\"{{ frontend_url }}/incidents\" class=\"btn\">Go to Incidents</a></p>"
)

# ---------------------------------------------------------------------------
# incident_digest
# Context: assignee_name, count, noun,
#          incidents[{display_id,title,severity,state,url}],
#          recent_events[{display_id,kind,actor}], frontend_url
# ---------------------------------------------------------------------------
_INCIDENT_DIGEST_BODY = (
    "<h1>Incident digest</h1>"
    "<p>Hi {{ assignee_name }}, you have "
    "<strong style=\"color:#f0f4ff;\">{{ count }} active {{ noun }}</strong> assigned to you.</p>"
    "<hr class=\"divider\">"
    "<p style=\"font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;margin-bottom:12px;\">Active Incidents</p>"
    "{% for inc in incidents %}"
    "<div class=\"incident-card\">"
    "<div class=\"incident-id\">{{ inc.display_id }}</div>"
    "<div class=\"incident-title\">{{ inc.title }}</div>"
    "<div class=\"meta\">"
    "<span class=\"badge badge-{{ inc.severity }}\">{{ inc.severity }}</span>"
    "&nbsp;&middot;&nbsp;{{ inc.state }}"
    "</div>"
    "<div style=\"margin-top:10px;\"><a href=\"{{ inc.url }}\">Open incident &rarr;</a></div>"
    "</div>"
    "{% endfor %}"
    "{% if recent_events %}"
    "<hr class=\"divider\">"
    "<p style=\"font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;margin-bottom:12px;\">Activity in the last 24h</p>"
    "{% for ev in recent_events %}"
    "<div class=\"event-row\">"
    "<span style=\"color:#3b82f6;font-family:monospace;font-size:12px;\">{{ ev.display_id }}</span>"
    " &mdash; {{ ev.kind }} by {{ ev.actor }}"
    "</div>"
    "{% endfor %}"
    "{% endif %}"
    "<hr class=\"divider\">"
    "<p><a href=\"{{ frontend_url }}/incidents\" class=\"btn\">View all incidents</a></p>"
)

# ---------------------------------------------------------------------------
# contact_notified
# Context: contact_name, display_id, title, severity, frontend_url
# ---------------------------------------------------------------------------
_CONTACT_NOTIFIED_BODY = (
    "<h1>Security incident notification</h1>"
    "<p>Hi {{ contact_name }},</p>"
    "<p>We wanted to keep you informed about a security incident that may be relevant to you.</p>"
    "<div class=\"incident-card\">"
    "<p class=\"incident-id\">{{ display_id }}</p>"
    "<p class=\"incident-title\">{{ title }}</p>"
    "<p class=\"meta\">Severity: <span class=\"badge badge-{{ severity }}\">{{ severity }}</span></p>"
    "</div>"
    "<p style=\"font-size:13px;color:#64748b;\">No action is required at this time. "
    "Our team is actively monitoring the situation.</p>"
)

# ---------------------------------------------------------------------------
# contact_questioned
# Context: contact_name, display_id, title, severity, message, frontend_url
# ---------------------------------------------------------------------------
_CONTACT_QUESTIONED_BODY = (
    "<h1>Security incident — your input requested</h1>"
    "<p>Hi {{ contact_name }},</p>"
    "<p>Our security team is investigating an incident and would appreciate your assistance.</p>"
    "<div class=\"incident-card\">"
    "<p class=\"incident-id\">{{ display_id }}</p>"
    "<p class=\"incident-title\">{{ title }}</p>"
    "<p class=\"meta\">Severity: <span class=\"badge badge-{{ severity }}\">{{ severity }}</span></p>"
    "</div>"
    "<p>{{ message }}</p>"
    "<p style=\"font-size:13px;color:#64748b;\">You can reply directly to this email.</p>"
)

# ---------------------------------------------------------------------------
# invite
# Context: full_name, org_name, invite_url, frontend_url
# ---------------------------------------------------------------------------
_INVITE_BODY = (
    "<h1>You&rsquo;re invited!</h1>"
    "<p>Hi {{ full_name }},</p>"
    "<p>Your signup request for <strong style=\"color:#f0f4ff;\">{{ org_name }}</strong> has been approved.</p>"
    "<p>Use the button below to create your account. "
    "This link expires in <strong style=\"color:#f0f4ff;\">7 days</strong>.</p>"
    "<hr class=\"divider\">"
    "<p><a href=\"{{ invite_url }}\" class=\"btn\">Create your account &rarr;</a></p>"
    "<hr class=\"divider\">"
    "<p style=\"font-size:13px;color:#64748b;\">If the button doesn&rsquo;t work, copy this link:<br>"
    "<span style=\"word-break:break-all;color:#3b82f6;\">{{ invite_url }}</span></p>"
    "<p style=\"font-size:13px;color:#64748b;\">If you did not request access, please ignore this email.</p>"
)

# ---------------------------------------------------------------------------
# rejection
# Context: full_name, org_name, rejection_reason, rejection_note, frontend_url
# ---------------------------------------------------------------------------
_REJECTION_BODY = (
    "<h1>Signup request update</h1>"
    "<p>Hi {{ full_name }},</p>"
    "<p>Unfortunately, your signup request for <strong style=\"color:#f0f4ff;\">{{ org_name }}</strong> "
    "has not been approved at this time.</p>"
    "<hr class=\"divider\">"
    "<p style=\"font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;\">Reason</p>"
    "<p style=\"color:#f0f4ff;\">{{ rejection_reason }}</p>"
    "{% if rejection_note %}<p>{{ rejection_note }}</p>{% endif %}"
    "<hr class=\"divider\">"
    "<p style=\"font-size:13px;color:#64748b;\">You may resubmit after 24 hours if circumstances change.</p>"
)

# ---------------------------------------------------------------------------
# signup_request  (admin notification)
# Context: full_name, email, org_name, intended_use, review_url, frontend_url
# ---------------------------------------------------------------------------
_SIGNUP_REQUEST_BODY = (
    "<h1>New signup request</h1>"
    "<p>A new signup request has been submitted and requires your review.</p>"
    "<hr class=\"divider\">"
    "<table cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"100%\">"
    "<tr>"
    "<td style=\"padding:8px 0;font-size:13px;color:#64748b;width:120px;\">Name</td>"
    "<td style=\"padding:8px 0;font-size:14px;color:#f0f4ff;\">{{ full_name }}</td>"
    "</tr>"
    "<tr>"
    "<td style=\"padding:8px 0;font-size:13px;color:#64748b;\">Email</td>"
    "<td style=\"padding:8px 0;font-size:14px;color:#f0f4ff;\">{{ email }}</td>"
    "</tr>"
    "<tr>"
    "<td style=\"padding:8px 0;font-size:13px;color:#64748b;\">Organisation</td>"
    "<td style=\"padding:8px 0;font-size:14px;color:#f0f4ff;\">{{ org_name }}</td>"
    "</tr>"
    "<tr>"
    "<td style=\"padding:8px 0;font-size:13px;color:#64748b;vertical-align:top;\">Intended use</td>"
    "<td style=\"padding:8px 0;font-size:14px;color:#f0f4ff;white-space:pre-wrap;\">{{ intended_use }}</td>"
    "</tr>"
    "</table>"
    "<hr class=\"divider\">"
    "<p><a href=\"{{ review_url }}\" class=\"btn\">Review request &rarr;</a></p>"
)

# ---------------------------------------------------------------------------
# test
# Context: recipient_name, frontend_url
# ---------------------------------------------------------------------------
_TEST_BODY = (
    "<h1>Test email</h1>"
    "<p>Hi {{ recipient_name }},</p>"
    "<p>This is a test email from <strong style=\"color:#f0f4ff;\">vels.online</strong> "
    "confirming that email delivery is working correctly.</p>"
    "<hr class=\"divider\">"
    "<p style=\"font-size:13px;color:#64748b;\">No action is required. You can safely ignore this message.</p>"
)

# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------
DEFAULT_TEMPLATES = {
    "notification_digest": {
        "description": "Digest of in-app notifications sent to users",
        "subject": "{{ count }} notification{{ count|pluralize }} from vels.online",
        "html_body": _base("Notifications", _NOTIF_DIGEST_BODY),
    },
    "incident_digest": {
        "description": "Daily digest of active incidents sent to assignees",
        "subject": "[vels.online] Incident digest: {{ count }} {{ noun }} assigned to you",
        "html_body": _base("Incident digest", _INCIDENT_DIGEST_BODY),
    },
    "invite": {
        "description": "Account invitation sent when a signup request is approved",
        "subject": "Your invitation to vels.online",
        "html_body": _base("You're invited", _INVITE_BODY),
    },
    "rejection": {
        "description": "Sent to the applicant when a signup request is rejected",
        "subject": "Your signup request to vels.online",
        "html_body": _base("Signup request update", _REJECTION_BODY),
    },
    "signup_request": {
        "description": "Sent to staff when a new signup request is submitted",
        "subject": "[vels.online] New signup request: {{ org_name }}",
        "html_body": _base("New signup request", _SIGNUP_REQUEST_BODY),
    },
    "contact_notified": {
        "description": "Sent to a contact when they are linked to an incident with role=notified",
        "subject": "[vels.online] Security incident notification: {{ display_id }}",
        "html_body": _base("Security incident notification", _CONTACT_NOTIFIED_BODY),
    },
    "contact_questioned": {
        "description": "Sent to a contact when they are linked to an incident with role=questioned",
        "subject": "[vels.online] Security incident — your input requested: {{ display_id }}",
        "html_body": _base("Security incident — your input requested", _CONTACT_QUESTIONED_BODY),
    },
    "test": {
        "description": "Test email sent from the admin dashboard",
        "subject": "[vels.online] Test email",
        "html_body": _base("Test email", _TEST_BODY),
    },
}
