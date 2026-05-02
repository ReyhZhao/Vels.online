from django.apps import AppConfig


class SecurityConfig(AppConfig):
    name = "security"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import security.signals  # noqa: F401
