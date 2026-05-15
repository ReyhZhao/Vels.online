from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0002_add_system_alert_notification_prefs"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="shown_inapp",
            field=models.BooleanField(default=True),
        ),
    ]
