import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("security", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Download",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=255)),
                ("s3_key", models.CharField(blank=True, max_length=500)),
                (
                    "platform",
                    models.CharField(
                        choices=[
                            ("windows", "Windows"),
                            ("linux", "Linux"),
                            ("macos", "macOS"),
                            ("all", "All"),
                        ],
                        default="all",
                        max_length=20,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("agent", "Agent"),
                            ("tool", "Tool"),
                            ("config", "Config"),
                        ],
                        default="agent",
                        max_length=20,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="downloads",
                        to="security.organization",
                    ),
                ),
            ],
        ),
    ]
