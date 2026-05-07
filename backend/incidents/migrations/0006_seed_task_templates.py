from django.db import migrations

SEED_TEMPLATES = {
    "phishing": {
        "name": "Phishing Response Playbook",
        "description": "Baseline response playbook for phishing incidents.",
        "items": [
            (1, "Quarantine reported email", "Extract indicators from the email: URLs, attachments, sender address, and email headers."),
            (2, "Search email gateway for similar messages", "Search across all mailboxes for the same sender, subject line, or embedded URLs to identify further recipients."),
            (3, "Block IOCs in firewall and proxy", "Block the sending domain and any embedded URLs or attachment hashes in the firewall, email gateway, and web proxy."),
            (4, "Identify and notify affected recipients", "Notify recipients who received the email of the phishing attempt and provide guidance on what to do."),
            (5, "Reset credentials for users who engaged", "Force password reset and session revocation for any user who clicked a link or entered credentials."),
            (6, "Check endpoint telemetry for post-click activity", "Review EDR and SIEM for downloads, process executions, or lateral movement following any click events."),
            (7, "Draft incident summary and customer notification", "Prepare a summary of the incident, indicators found, actions taken, and customer-facing notification if required."),
        ],
    },
    "malware": {
        "name": "Malware Response Playbook",
        "description": "Baseline response playbook for malware incidents.",
        "items": [
            (1, "Isolate affected endpoint(s) from network", "Place impacted hosts into network isolation via EDR or switch ACL to prevent lateral movement."),
            (2, "Preserve forensic artifacts", "Capture memory dump, process list, active connections, and disk image before remediation."),
            (3, "Identify malware family and IOCs", "Analyse samples or telemetry to determine malware family, C2 addresses, registry keys, and file hashes."),
            (4, "Block IOCs across controls", "Add IOCs to EDR blocklist, firewall deny rules, and DNS sinkhole."),
            (5, "Scan for lateral movement or additional infections", "Search SIEM and EDR for the same IOCs across the environment to detect spread."),
            (6, "Remediate and verify clean state", "Remove malware, verify integrity, patch the exploit path, and restore from clean backup if necessary."),
            (7, "Update detection rules and document", "Create or tune detection rules based on the incident, document findings, and update the threat intel feed."),
        ],
    },
    "account_compromise": {
        "name": "Account Compromise Response Playbook",
        "description": "Baseline response playbook for compromised account incidents.",
        "items": [
            (1, "Reset credentials and revoke active sessions", "Immediately force password reset and invalidate all active sessions and tokens for the compromised account."),
            (2, "Verify MFA is in place and was not bypassed", "Confirm MFA is enrolled and check logs for any MFA bypass attempts or fallback authentication."),
            (3, "Review account activity logs for the past 30 days", "Audit login history, data access, permission changes, and resource access for the compromised account."),
            (4, "Check for persistence mechanisms", "Look for new admin accounts, mail forwarding rules, OAuth grants, and scheduled tasks created by the attacker."),
            (5, "Determine initial access vector", "Identify how the account was compromised: phishing, credential stuffing, leaked password, or MFA fatigue."),
            (6, "Notify affected user and stakeholders", "Inform the user, their manager, and any relevant team leads of the compromise and remediation steps."),
            (7, "Monitor account for re-compromise", "Place the account under elevated monitoring for 30 days and review any anomalous sign-ins."),
        ],
    },
    "data_exfiltration": {
        "name": "Data Exfiltration Response Playbook",
        "description": "Baseline response playbook for data exfiltration incidents.",
        "items": [
            (1, "Identify exfiltration vector and timeline", "Determine how data was exfiltrated (email, USB, cloud upload, API) and establish the start and end of the activity window."),
            (2, "Preserve evidence", "Preserve egress logs, network captures, DLP alerts, and endpoint telemetry as evidence."),
            (3, "Block exfiltration channel", "Immediately block the vector used (revoke API credentials, block cloud destination, disable USB on endpoint)."),
            (4, "Enumerate data scope", "Determine exactly what data was taken, including volume, sensitivity classification, and data subject categories."),
            (5, "Assess regulatory notification obligations", "Evaluate whether the exfiltration triggers mandatory notification under GDPR, NIS2, or other applicable regulations."),
            (6, "Notify legal, management, and affected parties", "Escalate to legal counsel and executive management; initiate breach notification workflow if required."),
            (7, "Remediate the control gap", "Patch or reconfigure the control that was bypassed (DLP policy, access control, network egress filter)."),
        ],
    },
    "policy_violation": {
        "name": "Policy Violation Response Playbook",
        "description": "Baseline response playbook for internal policy violation incidents.",
        "items": [
            (1, "Collect and preserve evidence", "Gather logs, screenshots, and user activity records that document the violation while maintaining chain of custody."),
            (2, "Determine scope and severity", "Assess whether the violation was accidental or deliberate, isolated or systemic, and what data or systems were affected."),
            (3, "Contain any ongoing exposure", "If the violation involves ongoing data exposure or system misuse, contain it immediately."),
            (4, "Escalate to HR and legal", "Notify HR and legal counsel according to the disciplinary and incident response policy."),
            (5, "Notify affected parties and management", "Inform relevant stakeholders including the employee's manager and any impacted data owners."),
            (6, "Review and update policies or controls", "Identify the policy or control gap that permitted the violation and propose remediation."),
        ],
    },
}


def seed_templates(apps, schema_editor):
    Subject = apps.get_model("incidents", "Subject")
    TaskTemplate = apps.get_model("incidents", "TaskTemplate")
    TaskTemplateItem = apps.get_model("incidents", "TaskTemplateItem")

    for subject_slug, data in SEED_TEMPLATES.items():
        try:
            subject = Subject.objects.get(slug=subject_slug)
        except Subject.DoesNotExist:
            continue

        template, _ = TaskTemplate.objects.update_or_create(
            subject=subject,
            name=data["name"],
            defaults={
                "description": data["description"],
                "is_auto_apply": True,
                "archived": False,
            },
        )

        existing_titles = set(template.items.values_list("title", flat=True))
        for order, title, description in data["items"]:
            if title not in existing_titles:
                TaskTemplateItem.objects.create(
                    template=template,
                    title=title,
                    description=description,
                    display_order=order,
                )


def unseed_templates(apps, schema_editor):
    TaskTemplate = apps.get_model("incidents", "TaskTemplate")
    names = [v["name"] for v in SEED_TEMPLATES.values()]
    TaskTemplate.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0005_task_template"),
    ]

    operations = [
        migrations.RunPython(seed_templates, reverse_code=unseed_templates),
    ]
