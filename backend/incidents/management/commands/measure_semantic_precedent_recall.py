"""Background research job for issue #657: would semantic (embedding) precedent retrieval
recover **Precedents** the current entity/keyword `Q` misses?

Runs the retrospective, correction-anchored measurement in `incidents.memory.semantic_measure`
and prints a go/no-go report. Stands up **no** vector store and touches **no** hot triage
path — it only reads history and calls an embedding endpoint. Per ADR-0030 v1 deliberately
has no vector store; this command produces the evidence to decide whether #657 is worth
building. Strictly per-org throughout (ADR-0031).

The embedder defaults to **Ollama Cloud** (the production triage provider) and can be
pointed at Gemini via ``EMBED_MEASURE_PROVIDER=gemini``. It is built only here — the
production `BaseTriageProvider` abstraction stays chat-only until (if) a serving path ships.

    docker compose exec backend python manage.py measure_semantic_precedent_recall --days 90
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from incidents.memory import semantic_measure as sm


# ── embedders (the only real-provider glue; semantic_measure stays provider-free) ──


def _ollama_embedder(batch_size=64):
    import ollama

    base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    api_key = getattr(settings, "OLLAMA_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    timeout = getattr(settings, "OLLAMA_TIMEOUT_S", 60.0)
    model = getattr(settings, "OLLAMA_EMBED_MODEL", "embeddinggemma")
    client = ollama.Client(host=base_url, headers=headers, timeout=timeout)

    def embed(texts):
        out = []
        for i in range(0, len(texts), batch_size):
            resp = client.embed(model=model, input=texts[i:i + batch_size])
            out.extend(resp.embeddings)
        return out

    return embed


def _gemini_embedder(batch_size=100):
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise CommandError("EMBED_MEASURE_PROVIDER=gemini but GEMINI_API_KEY is not set.")
    from google import genai

    client = genai.Client(api_key=api_key)
    model = getattr(settings, "GEMINI_EMBED_MODEL", "text-embedding-004")

    def embed(texts):
        out = []
        for i in range(0, len(texts), batch_size):
            resp = client.models.embed_content(model=model, contents=texts[i:i + batch_size])
            out.extend(e.values for e in resp.embeddings)
        return out

    return embed


def build_embedder(provider=None):
    provider = (provider or getattr(settings, "EMBED_MEASURE_PROVIDER", "ollama")).lower()
    if provider == "ollama":
        return _ollama_embedder()
    if provider == "gemini":
        return _gemini_embedder()
    raise CommandError(f"Unknown EMBED_MEASURE_PROVIDER '{provider}' (expected ollama|gemini).")


class Command(BaseCommand):
    help = "Measure whether embedding-based precedent retrieval would recover cases the " \
           "entity/keyword retrieval misses (issue #657 go/no-go evidence)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90,
                            help="Look back this many days of Classification Corrections.")
        parser.add_argument("--top-k", type=int, default=sm.DEFAULT_TOP_K,
                            help="Retrieval budget for both keyword and embedding.")
        parser.add_argument("--min-sample", type=int, default=sm.MIN_SAMPLE,
                            help="Withhold the verdict below this many scored (retrievable) cases.")
        parser.add_argument("--provider", choices=["ollama", "gemini"], default=None,
                            help="Override EMBED_MEASURE_PROVIDER for this run.")
        parser.add_argument("--limit", type=int, default=None,
                            help="Cap corrections processed (smoke-test aid).")

    def handle(self, *args, **opts):
        from incidents.models import ClassificationCorrection

        since = timezone.now() - timedelta(days=opts["days"])
        corrections = (
            ClassificationCorrection.objects
            .filter(created_at__gte=since)
            .select_related("incident", "human_subject")
            .order_by("created_at")
        )
        if opts["limit"]:
            corrections = corrections[:opts["limit"]]

        total = corrections.count() if opts["limit"] is None else len(corrections)
        if total == 0:
            self.stdout.write(self.style.WARNING(
                f"No Classification Corrections in the last {opts['days']} days — nothing to measure."
            ))
            return

        provider = (opts["provider"] or getattr(settings, "EMBED_MEASURE_PROVIDER", "ollama")).lower()
        model = getattr(settings, "GEMINI_EMBED_MODEL" if provider == "gemini"
                        else "OLLAMA_EMBED_MODEL", "?")
        self.stdout.write(self.style.NOTICE(
            f"Embedder: provider={provider}, model={model}, corrections={total}"
        ))
        embedder = build_embedder(opts["provider"])

        # Fail fast on a misconfigured embedder — a single tiny vector before any DB work,
        # so a bad key/model surfaces one legible line instead of a mid-run traceback.
        try:
            probe = embedder(["preflight"])
            if not probe or not probe[0]:
                raise CommandError("embedder returned an empty vector on preflight.")
        except CommandError:
            raise
        except Exception as exc:
            other = "gemini" if provider == "ollama" else "ollama"
            hint = ""
            if provider == "ollama":
                hint = ("\nNote: Ollama Cloud (ollama.com) serves NO embedding models — point "
                        "OLLAMA_BASE_URL at a self-hosted Ollama (e.g. http://ollama-embed:11434) "
                        "with the model pulled, and clear OLLAMA_API_KEY for the local endpoint.")
            raise CommandError(
                f"Embedder '{provider}' (model={model}) failed on a preflight embed: {exc}{hint}"
                f"\nCheck credentials/model, or retry with --provider {other}."
            ) from exc

        report = sm.run_measurement(
            corrections, embedder, top_k=opts["top_k"], min_sample=opts["min_sample"]
        )
        self._print_report(report, days=opts["days"])

    def _print_report(self, report, *, days):
        w = self.stdout.write
        b = report.buckets
        w("")
        w("═" * 68)
        w("  Semantic precedent-recall measurement (issue #657)")
        w(f"  window: last {days} days   |   embedder: "
          f"{getattr(settings, 'EMBED_MEASURE_PROVIDER', 'ollama')}")
        w("═" * 68)
        w(f"  Corrections scored (subject corrections): {report.scored}")
        w(f"  Skipped (no human subject):               {report.skipped_no_subject}")
        w("-" * 68)
        w("  Where the RIGHT prior landed:")
        w(f"    corpus_gap          (no such prior existed) : {b[sm.CORPUS_GAP]}")
        w(f"    keyword_covered     (keyword already got it) : {b[sm.KEYWORD_COVERED]}")
        w(f"    embedding_recovered (keyword MISSED, embed got it) : "
          f"{b[sm.EMBEDDING_RECOVERED]}  ⭐")
        w(f"    both_missed         (prior existed, both missed)   : {b[sm.BOTH_MISSED]}")
        w("-" * 68)
        headline = report.headline
        headline_str = "n/a" if headline is None else f"{headline:.1%}"
        w(f"  Retrievable cases (denominator): {report.exists_total}")
        w(f"  HEADLINE  embedding_recovered / retrievable = {headline_str}")
        w(f"  Decision bands: build ≥ {report.build_threshold:.0%}, "
          f"close < {report.close_threshold:.0%}, min sample {report.min_sample}")
        verdict = report.verdict
        styler = {
            sm.VERDICT_BUILD: self.style.SUCCESS,
            sm.VERDICT_CLOSE: self.style.SUCCESS,
            sm.VERDICT_INSUFFICIENT: self.style.WARNING,
            sm.VERDICT_INCONCLUSIVE: self.style.WARNING,
        }.get(verdict, self.style.NOTICE)
        w(f"  VERDICT: {styler(verdict.upper())}")
        w("═" * 68)

        if report.per_org:
            w("  Per-org breakdown (org_id: gap/keyword/embed/both):")
            for org_id, counts in sorted(report.per_org.items()):
                w(f"    org {org_id}: "
                  f"{counts[sm.CORPUS_GAP]}/{counts[sm.KEYWORD_COVERED]}/"
                  f"{counts[sm.EMBEDDING_RECOVERED]}/{counts[sm.BOTH_MISSED]}")

        if report.recovered_examples:
            w("-" * 68)
            w("  Embedding-recovered examples — EYEBALL THESE before trusting the number")
            w("  (are they genuinely the same case, or spurious semantic neighbours?):")
            for o in report.recovered_examples:
                w(f"    {o.display_id} (org {o.org_id}) → subject '{o.human_subject}'; "
                  f"right prior(s) {sorted(o.prior_ids)} reached only by embedding "
                  f"{sorted(o.embedding_ids & o.prior_ids)}")
        w("")
