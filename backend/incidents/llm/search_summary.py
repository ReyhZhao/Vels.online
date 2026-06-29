"""Readable-summary generator for scheduled-search incidents (#644).

A thin wrapper over the existing LLM infra, mirroring
``incidents.llm.report_summary``. It turns the matched-document evidence of a
scheduled-search Incident into a short, analyst-readable summary that replaces the
raw ``source_ref`` JSON that used to be dumped into the incident description. The
raw data still lives on each linked Alert; this is purely a readability layer.

Generation is best-effort: a failure (provider unavailable, misconfigured, or
erroring) returns an empty string so incident creation never fails because the
summary could not be written.
"""
import logging

from incidents.llm.factory import get_search_summary_provider

logger = logging.getLogger(__name__)


def generate_search_incident_summary(evidence: dict) -> str:
    """Return analyst-readable summary prose for the given matched-document evidence.

    Returns an empty string if the provider is unavailable or errors.
    """
    try:
        provider = get_search_summary_provider()
        return provider.generate_search_incident_summary(evidence) or ""
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("generate_search_incident_summary: LLM call failed: %s", exc)
        return ""
