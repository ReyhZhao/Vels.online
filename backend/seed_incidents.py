#!/usr/bin/env python
"""Seed 100 random incidents for dev. Run with: python manage.py shell < seed_incidents.py"""
import os
import random
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import User
from incidents.models import Incident, Subject
from incidents.services.identifiers import next_display_id
from security.models import Organization

TITLES = [
    "Suspicious login from unknown IP",
    "Malware detected on endpoint",
    "Brute force attack on SSH",
    "Privilege escalation attempt",
    "Data exfiltration via DNS tunneling",
    "Ransomware behaviour detected",
    "Unauthorized access to admin panel",
    "Phishing email campaign detected",
    "SQL injection attempt on web app",
    "Lateral movement detected in network",
    "Credential stuffing attack",
    "Anomalous outbound traffic spike",
    "Rootkit detected on server",
    "Cryptominer installed on host",
    "Config file with exposed secrets found",
    "Suspicious PowerShell execution",
    "Reverse shell connection detected",
    "Failed MFA attempts from multiple locations",
    "DLP policy violation — PII in email",
    "Vulnerability scan from external IP",
    "Suspicious scheduled task created",
    "New admin account created without approval",
    "Log forwarding disabled on critical host",
    "Excessive failed authentications",
    "Suspicious file download from C2 domain",
]

DESCRIPTIONS = [
    "Automated detection flagged this event for review.",
    "Alert triggered by EDR rule. Analyst review required.",
    "SIEM correlation rule matched pattern associated with known threat actor.",
    "Wazuh agent reported anomalous behaviour. Pending triage.",
    "Network sensor detected unusual traffic. Host isolation may be required.",
    "User reported suspicious activity. Initial investigation underway.",
    "Threat intelligence feed matched observed indicators.",
    "",
]

org = Organization.objects.first()
if not org:
    raise SystemExit("No Organization found — create one first.")

users = list(User.objects.filter(is_active=True))
subjects = list(Subject.objects.filter(archived=False))

severities = [c[0] for c in Incident.SEVERITY_CHOICES]
severity_weights = [5, 20, 40, 25, 10]  # critical, high, medium, low, info

states = [c[0] for c in Incident.STATE_CHOICES]
state_weights = [30, 15, 25, 10, 5, 10, 5]

sources = [c[0] for c in Incident.SOURCE_CHOICES]
tlps = [c[0] for c in Incident.TLP_CHOICES]
paps = [c[0] for c in Incident.PAP_CHOICES]

created = 0
for _ in range(100):
    state = random.choices(states, weights=state_weights)[0]
    closure = None
    if state in (Incident.STATE_RESOLVED, Incident.STATE_CLOSED):
        closure = random.choice([c[0] for c in Incident.CLOSURE_REASON_CHOICES])

    incident = Incident.objects.create(
        organization=org,
        display_id=next_display_id(),
        title=random.choice(TITLES),
        description=random.choice(DESCRIPTIONS),
        severity=random.choices(severities, weights=severity_weights)[0],
        source_kind=random.choice(sources),
        tlp=random.choice(tlps),
        pap=random.choice(paps),
        state=state,
        closure_reason=closure,
        subject=random.choice(subjects) if subjects and random.random() > 0.3 else None,
        assignee=random.choice(users) if users and random.random() > 0.4 else None,
        created_by=random.choice(users) if users else None,
    )
    created += 1

print(f"Created {created} incidents.")
