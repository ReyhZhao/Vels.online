from importlib import import_module

from django.conf import settings

_DEFAULT_PROVIDER = "exceptions.llm.gemini.GeminiFlashProvider"


def get_llm_provider():
    """Instantiate and return the configured LLM provider."""
    provider_path = getattr(settings, "EXCEPTION_LLM_PROVIDER", _DEFAULT_PROVIDER)
    module_path, class_name = provider_path.rsplit(".", 1)
    module = import_module(module_path)
    cls = getattr(module, class_name)
    return cls()
