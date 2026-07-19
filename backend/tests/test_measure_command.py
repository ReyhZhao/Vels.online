"""The measure_semantic_precedent_recall management command (issue #657 research job).

Covers embedder selection (Ollama Cloud by default, Gemini opt-in) and the end-to-end
command wiring with an injected fake embedder — no real provider is ever called.
"""
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from incidents.management.commands import measure_semantic_precedent_recall as cmd
from incidents.models import ClassificationCorrection, IOC, Incident, Subject
from security.models import Organization


def bow_embedder(texts):
    vocab = sorted({tok for text in texts for tok in text.lower().split()})
    return [[float(text.lower().split().count(w)) for w in vocab] for text in texts]


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


def test_build_embedder_defaults_to_ollama(settings):
    settings.EMBED_MEASURE_PROVIDER = "ollama"
    assert callable(cmd.build_embedder())  # constructs an Ollama client, no network call


def test_build_embedder_gemini_requires_api_key(settings):
    settings.EMBED_MEASURE_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = ""
    with pytest.raises(CommandError):
        cmd.build_embedder()


def test_build_embedder_rejects_unknown_provider():
    with pytest.raises(CommandError):
        cmd.build_embedder("pinecone")


def test_retrying_recovers_after_transient_timeouts(monkeypatch):
    import httpx
    monkeypatch.setattr(cmd.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < cmd._EMBED_RETRIES:
            raise httpx.ReadTimeout("slow")
        return "ok"

    assert cmd._retrying(flaky, what="test") == "ok"
    assert calls["n"] == cmd._EMBED_RETRIES


def test_retrying_reraises_after_exhausting_retries(monkeypatch):
    import httpx
    monkeypatch.setattr(cmd.time, "sleep", lambda _s: None)

    def always_down():
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        cmd._retrying(always_down, what="test")


@pytest.mark.django_db
def test_command_reports_nothing_when_no_corrections(acme):
    out = StringIO()
    call_command("measure_semantic_precedent_recall", "--days", "30", stdout=out)
    assert "nothing to measure" in out.getvalue()


@pytest.mark.django_db
def test_command_preflight_fails_fast_on_a_broken_embedder(acme, monkeypatch):
    def boom(texts):
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr(cmd, "build_embedder", lambda provider=None: boom)
    subj = Subject.objects.create(name="Brute Force", slug="sem-cmd-boom")
    query = Incident.objects.create(
        organization=acme, title="x", description="y", display_id="INC-2026-9100", state="new",
    )
    ClassificationCorrection.objects.create(incident=query, human_subject=subj)

    with pytest.raises(CommandError, match="preflight"):
        call_command("measure_semantic_precedent_recall", stdout=StringIO())


@pytest.mark.django_db
def test_command_runs_end_to_end_with_injected_embedder(acme, monkeypatch):
    monkeypatch.setattr(cmd, "build_embedder", lambda provider=None: bow_embedder)
    subj = Subject.objects.create(name="Brute Force", slug="sem-cmd-bf")
    query = Incident.objects.create(
        organization=acme, title="repeated failed login", description="ssh brute force",
        display_id="INC-2026-9001", state="new",
    )
    IOC.objects.create(incident=query, kind="ip", value="1.2.3.4")
    prior = Incident.objects.create(
        organization=acme, title="repeated failed login", description="ssh brute force",
        display_id="INC-2026-9000", state="closed", closure_reason="resolved", subject=subj,
    )
    IOC.objects.create(incident=prior, kind="ip", value="9.9.9.9")
    Incident.objects.filter(pk=prior.pk).update(
        updated_at=query.created_at - timedelta(seconds=1)
    )
    ClassificationCorrection.objects.create(incident=query, human_subject=subj)

    out = StringIO()
    call_command("measure_semantic_precedent_recall", "--min-sample", "1", stdout=out)
    text = out.getvalue()
    assert "VERDICT" in text
    assert "embedding_recovered" in text
    assert "INC-2026-9001" in text  # the recovered example is eyeballable in the output
