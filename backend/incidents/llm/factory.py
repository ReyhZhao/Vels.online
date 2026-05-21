from importlib import import_module

from django.conf import settings

from .base import BaseTriageProvider, TriageConfigError

_DEFAULT_PROVIDER = "incidents.llm.gemini.GeminiTriageProvider"


def get_triage_provider() -> BaseTriageProvider:
    provider_path = getattr(settings, "TRIAGE_LLM_PROVIDER", _DEFAULT_PROVIDER)
    module_path, class_name = provider_path.rsplit(".", 1)
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise TriageConfigError(
            f"TRIAGE_LLM_PROVIDER '{provider_path}' module cannot be imported: {exc}"
        ) from exc
    try:
        cls = getattr(module, class_name)
    except AttributeError:
        raise TriageConfigError(
            f"TRIAGE_LLM_PROVIDER '{provider_path}': class '{class_name}' not found in module '{module_path}'."
        )
    try:
        instance = cls()
    except TypeError as exc:
        raise TriageConfigError(
            f"TRIAGE_LLM_PROVIDER '{provider_path}' could not be instantiated: {exc}"
        ) from exc
    if not isinstance(instance, BaseTriageProvider):
        raise TriageConfigError(
            f"TRIAGE_LLM_PROVIDER '{provider_path}' is not a BaseTriageProvider subclass. "
            f"Use 'incidents.llm.ollama.OllamaTriageProvider' for Ollama."
        )
    return instance
