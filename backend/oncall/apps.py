from django.apps import AppConfig


class OncallConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "oncall"

    def ready(self):
        import oncall.signals  # noqa: F401
