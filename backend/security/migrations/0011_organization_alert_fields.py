from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("security", "0010_organization_triage_prompt_context"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="alert_match_lookback_days",
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.AddField(
            model_name="organization",
            name="alert_auto_promote_threshold",
            field=models.PositiveIntegerField(default=5),
        ),
        migrations.AddField(
            model_name="organization",
            name="alert_auto_promote_window_minutes",
            field=models.PositiveIntegerField(default=60),
        ),
    ]
