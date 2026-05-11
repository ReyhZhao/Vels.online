from django.db import migrations


def seed_pool(apps, schema_editor):
    WazuhRuleIdPool = apps.get_model("exceptions", "WazuhRuleIdPool")
    if not WazuhRuleIdPool.objects.exists():
        WazuhRuleIdPool.objects.create(last_assigned_id=199999)


def unseed_pool(apps, schema_editor):
    WazuhRuleIdPool = apps.get_model("exceptions", "WazuhRuleIdPool")
    WazuhRuleIdPool.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("exceptions", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_pool, reverse_code=unseed_pool),
    ]
