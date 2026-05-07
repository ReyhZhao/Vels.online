from django.db import migrations

STARTER_SUBJECTS = [
    {"name": "Phishing", "slug": "phishing", "description": "Phishing attacks targeting users or systems."},
    {"name": "Malware", "slug": "malware", "description": "Malicious software including ransomware, trojans, and spyware."},
    {"name": "Account Compromise", "slug": "account_compromise", "description": "Unauthorised access to user or service accounts."},
    {"name": "Data Exfiltration", "slug": "data_exfiltration", "description": "Unauthorised transfer of data outside the organisation."},
    {"name": "Policy Violation", "slug": "policy_violation", "description": "Violation of internal security or acceptable-use policies."},
]


def seed_subjects(apps, schema_editor):
    Subject = apps.get_model("incidents", "Subject")
    for data in STARTER_SUBJECTS:
        Subject.objects.update_or_create(slug=data["slug"], defaults={"name": data["name"], "description": data["description"]})


def unseed_subjects(apps, schema_editor):
    Subject = apps.get_model("incidents", "Subject")
    Subject.objects.filter(slug__in=[s["slug"] for s in STARTER_SUBJECTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0003_subject_incident_fk"),
    ]

    operations = [
        migrations.RunPython(seed_subjects, reverse_code=unseed_subjects),
    ]
