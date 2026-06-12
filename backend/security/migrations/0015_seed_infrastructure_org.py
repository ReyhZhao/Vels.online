from django.db import migrations

# Keep these literals in sync with security.models (migrations must not import the
# live model — they use the historical model via apps.get_model).
INFRASTRUCTURE_ORG_SLUG = "infrastructure"
INFRASTRUCTURE_ORG_NAME = "Shared Infrastructure"


def seed_infrastructure_org(apps, schema_editor):
    """Idempotently create the single Infrastructure pseudo-org (ADR-0017).

    It owns no customer and has no wazuh_group members; it is the home for Shared
    Infrastructure events (agent.id="000") and is excluded from every real-tenant loop.
    """
    Organization = apps.get_model("security", "Organization")
    Organization.objects.get_or_create(
        is_infrastructure=True,
        defaults={
            "name": INFRASTRUCTURE_ORG_NAME,
            "slug": INFRASTRUCTURE_ORG_SLUG,
            "wazuh_group": "",
        },
    )


def unseed_infrastructure_org(apps, schema_editor):
    Organization = apps.get_model("security", "Organization")
    Organization.objects.filter(is_infrastructure=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("security", "0014_organization_is_infrastructure"),
    ]

    operations = [
        migrations.RunPython(seed_infrastructure_org, unseed_infrastructure_org),
    ]
