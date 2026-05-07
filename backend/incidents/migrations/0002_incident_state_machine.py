from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="incident",
            name="closure_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("resolved", "Resolved"),
                    ("false_positive", "False Positive"),
                    ("duplicate", "Duplicate"),
                    ("informational", "Informational"),
                    ("accepted_risk", "Accepted Risk"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="incident",
            name="state",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("triaged", "Triaged"),
                    ("in_progress", "In Progress"),
                    ("on_hold", "On Hold"),
                    ("resolved", "Resolved"),
                    ("closed", "Closed"),
                ],
                default="new",
                max_length=20,
            ),
        ),
    ]
