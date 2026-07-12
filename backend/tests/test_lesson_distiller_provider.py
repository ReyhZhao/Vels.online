"""The real providers must actually distil a Lesson (ADR-0030, #697 follow-up).

Regression guard: for a long time neither the Gemini nor the Ollama provider implemented
``distill_triage_lesson``, so every cluster that reached the distiller fell through to the
``BaseTriageProvider`` default that returns ``{}`` — producing a "No guidance" outcome on a
perfectly good cluster. These tests wire a mocked client and assert the providers parse the
model's JSON into the ``{"guidance", "selector"}`` contract the sweep consumes.
"""
import json
from unittest.mock import MagicMock, patch

from django.test import override_settings

from incidents.llm.gemini import _parse_distilled_lesson


def test_base_provider_still_defaults_to_no_lesson():
    from incidents.llm.base import BaseTriageProvider

    class Bare(BaseTriageProvider):
        def triage_incident(self, payload, extra_context=""):  # pragma: no cover - unused
            raise NotImplementedError

    assert Bare().distill_triage_lesson({"subject": "Malware"}) == {}


def test_parse_distilled_lesson_keeps_only_the_contract():
    parsed = _parse_distilled_lesson({
        "guidance": "  updater dropping a temp DLL is benign  ",
        "selector": "  when the process is a known updater  ",
        "confidence": 0.9,  # extraneous — must be dropped
    })
    assert parsed == {
        "guidance": "updater dropping a temp DLL is benign",
        "selector": "when the process is a known updater",
    }


def test_parse_distilled_lesson_degrades_malformed_to_empty():
    # Non-dict, or non-string fields, propose nothing rather than raising.
    assert _parse_distilled_lesson("nope") == {"guidance": "", "selector": ""}
    assert _parse_distilled_lesson({"guidance": None, "selector": 3}) == {"guidance": "", "selector": ""}
    assert _parse_distilled_lesson({}) == {"guidance": "", "selector": ""}


def _gemini_returning(raw_text):
    from incidents.llm.gemini import GeminiTriageProvider
    from google.genai import types as genai_types

    provider = MagicMock(spec=GeminiTriageProvider)
    response = MagicMock()
    response.text = raw_text
    provider._client = MagicMock()
    provider._client.models.generate_content.return_value = response
    provider._types = genai_types
    return provider


def test_gemini_distills_a_lesson_from_json():
    provider = _gemini_returning(json.dumps({
        "guidance": "A known updater writing a temp DLL is routine; treat as benign.",
        "selector": "when the source process is a signed updater",
    }))
    from incidents.llm.gemini import GeminiTriageProvider

    from django.conf import settings
    with patch.object(settings, "GEMINI_MODEL", "gemini-test", create=True):
        result = GeminiTriageProvider.distill_triage_lesson(provider, {"subject": "Malware", "incidents": []})

    assert result["guidance"].startswith("A known updater")
    assert result["selector"] == "when the source process is a signed updater"
    # The cluster payload was actually handed to the model.
    provider._client.models.generate_content.assert_called_once()


def test_gemini_strips_code_fence_and_reports_empty_guidance():
    fenced = "```json\n" + json.dumps({"guidance": "", "selector": ""}) + "\n```"
    provider = _gemini_returning(fenced)
    from incidents.llm.gemini import GeminiTriageProvider

    from django.conf import settings
    with patch.object(settings, "GEMINI_MODEL", "gemini-test", create=True):
        result = GeminiTriageProvider.distill_triage_lesson(provider, {"subject": "Malware", "incidents": []})

    assert result == {"guidance": "", "selector": ""}


def test_gemini_non_json_raises_triageerror():
    from incidents.llm.base import TriageError
    from incidents.llm.gemini import GeminiTriageProvider
    provider = _gemini_returning("the model refused to answer")

    from django.conf import settings
    import pytest
    with patch.object(settings, "GEMINI_MODEL", "gemini-test", create=True):
        with pytest.raises(TriageError):
            GeminiTriageProvider.distill_triage_lesson(provider, {"subject": "Malware"})


@override_settings(DISTILL_LLM_PROVIDER="incidents.llm.ollama.OllamaTriageProvider")
def test_distiller_provider_honours_its_own_knob():
    """The sweep selects its provider from DISTILL_LLM_PROVIDER, independent of triage."""
    from incidents.llm.factory import get_distiller_provider
    from incidents.llm.ollama import OllamaTriageProvider

    # OllamaTriageProvider.__init__ needs no external service to instantiate.
    provider = get_distiller_provider()
    assert isinstance(provider, OllamaTriageProvider)


@override_settings(DISTILL_LLM_PROVIDER="incidents.llm.gemini.GeminiTriageProvider")
def test_distiller_provider_selects_gemini_when_configured():
    from incidents.llm.factory import get_distiller_provider
    from incidents.llm.gemini import GeminiTriageProvider

    with patch.object(GeminiTriageProvider, "__init__", return_value=None):
        assert isinstance(get_distiller_provider(), GeminiTriageProvider)


def test_ollama_distills_a_lesson_from_json():
    from incidents.llm.ollama import OllamaTriageProvider

    provider = MagicMock(spec=OllamaTriageProvider)
    response = MagicMock()
    response.message.content = json.dumps({
        "guidance": "Repeated OpenCTI hits on outbound pings from LAN hosts are usually noise.",
        "selector": "",
    })
    provider._client = MagicMock()
    provider._client.chat.return_value = response
    provider._model = "mistral"

    result = OllamaTriageProvider.distill_triage_lesson(provider, {"subject": "Malware", "incidents": []})

    assert result["guidance"].startswith("Repeated OpenCTI")
    assert result["selector"] == ""
