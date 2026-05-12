from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0010_attachment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="incident",
            name="state",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("triaged", "Triaged"),
                    ("in_progress", "In Progress"),
                    ("on_hold", "On Hold"),
                    ("needs_tuning", "Needs Tuning"),
                    ("resolved", "Resolved"),
                    ("closed", "Closed"),
                ],
                default="new",
                max_length=20,
            ),
        ),
    ]
