from importlib import import_module

from django.conf import settings

_DEFAULT_PROVIDER = "incidents.llm.gemini.GeminiTriageProvider"


def get_triage_provider():
    provider_path = getattr(settings, "TRIAGE_LLM_PROVIDER", _DEFAULT_PROVIDER)
    module_path, class_name = provider_path.rsplit(".", 1)
    module = import_module(module_path)
    cls = getattr(module, class_name)
    return cls()
