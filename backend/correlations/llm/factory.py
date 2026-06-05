from importlib import import_module

from django.conf import settings

from .base import BaseDraftProvider, DraftConfigError

_DEFAULT_PROVIDER = "correlations.llm.gemini.GeminiDraftProvider"


def _load_provider(provider_path: str) -> BaseDraftProvider:
    module_path, class_name = provider_path.rsplit(".", 1)
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise DraftConfigError(
            f"Provider '{provider_path}' module cannot be imported: {exc}"
        ) from exc
    try:
        cls = getattr(module, class_name)
    except AttributeError:
        raise DraftConfigError(
            f"Provider '{provider_path}': class '{class_name}' not found in module '{module_path}'."
        )
    try:
        instance = cls()
    except TypeError as exc:
        raise DraftConfigError(
            f"Provider '{provider_path}' could not be instantiated: {exc}"
        ) from exc
    if not isinstance(instance, BaseDraftProvider):
        raise DraftConfigError(
            f"Provider '{provider_path}' is not a BaseDraftProvider subclass."
        )
    return instance


def get_draft_provider() -> BaseDraftProvider:
    provider_path = getattr(settings, "CORRELATION_LLM_PROVIDER", _DEFAULT_PROVIDER)
    return _load_provider(provider_path)
