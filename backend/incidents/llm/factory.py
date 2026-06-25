from importlib import import_module

from django.conf import settings

from .base import BaseTriageProvider, TriageConfigError

_DEFAULT_PROVIDER = "incidents.llm.gemini.GeminiTriageProvider"


def _load_provider(provider_path: str) -> BaseTriageProvider:
    module_path, class_name = provider_path.rsplit(".", 1)
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise TriageConfigError(
            f"Provider '{provider_path}' module cannot be imported: {exc}"
        ) from exc
    try:
        cls = getattr(module, class_name)
    except AttributeError:
        raise TriageConfigError(
            f"Provider '{provider_path}': class '{class_name}' not found in module '{module_path}'."
        )
    try:
        instance = cls()
    except TypeError as exc:
        raise TriageConfigError(
            f"Provider '{provider_path}' could not be instantiated: {exc}"
        ) from exc
    if not isinstance(instance, BaseTriageProvider):
        raise TriageConfigError(
            f"Provider '{provider_path}' is not a BaseTriageProvider subclass."
        )
    return instance


def get_triage_provider() -> BaseTriageProvider:
    provider_path = getattr(settings, "TRIAGE_LLM_PROVIDER", _DEFAULT_PROVIDER)
    return _load_provider(provider_path)


def get_closure_provider() -> BaseTriageProvider:
    provider_path = getattr(settings, "CLOSURE_LLM_PROVIDER", _DEFAULT_PROVIDER)
    return _load_provider(provider_path)


def get_assistant_provider() -> BaseTriageProvider:
    provider_path = getattr(settings, "INCIDENT_ASSISTANT_LLM_PROVIDER", _DEFAULT_PROVIDER)
    return _load_provider(provider_path)


def get_report_summary_provider() -> BaseTriageProvider:
    provider_path = getattr(settings, "REPORT_SUMMARY_LLM_PROVIDER", _DEFAULT_PROVIDER)
    return _load_provider(provider_path)
