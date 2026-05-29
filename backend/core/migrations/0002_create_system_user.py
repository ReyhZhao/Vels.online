from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.db import migrations


def create_system_user(apps, schema_editor):
    User = apps.get_model("auth", "User")
    User.objects.get_or_create(
        username="system",
        defaults={
            "email": "system@vels.online",
            "is_active": False,
            "password": UNUSABLE_PASSWORD_PREFIX,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_system_user, migrations.RunPython.noop),
    ]
