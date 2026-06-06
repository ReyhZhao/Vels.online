from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("correlations", "0003_add_search_rule_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="searchrule",
            name="correlation_key",
            field=models.CharField(
                choices=[
                    ("host.name", "Host (host.name)"),
                    ("source.ip", "Source IP (source.ip)"),
                    ("user.name", "Username (user.name)"),
                    ("file.hash.sha256", "File Hash (file.hash.sha256)"),
                    ("process.name", "Process (process.name)"),
                    ("none", "None (org-wide)"),
                ],
                default="none",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="searchruleleg",
            name="count",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
