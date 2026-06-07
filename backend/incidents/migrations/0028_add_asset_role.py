from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0027_add_scheduled_search_source_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="role",
            field=models.CharField(
                max_length=32,
                null=True,
                blank=True,
                choices=[
                    ("workstation", "Workstation"),
                    ("server", "Server"),
                    ("dns-server", "DNS Server"),
                    ("domain-controller", "Domain Controller"),
                    ("jumphost", "Jumphost"),
                    ("firewall", "Firewall"),
                    ("router", "Router"),
                    ("switch", "Switch"),
                    ("database-server", "Database Server"),
                    ("web-server", "Web Server"),
                    ("other", "Other"),
                ],
            ),
        ),
    ]
