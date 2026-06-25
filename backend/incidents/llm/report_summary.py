"""Executive-summary generator for incident Reports (PRD #621, ADR-0029).

A thin wrapper over the existing LLM infra. It is grounded ONLY on the
audience-filtered grounding (``incidents.services.report_grounding.build_report_grounding``)
so a ``customer`` summary can never mention internal findings. The generated prose
is frozen into the Report snapshot by the generation service — it is never re-run
when an existing Report is viewed or downloaded.
"""
import logging

from incidents.llm.factory import get_report_summary_provider

logger = logging.getLogger(__name__)


def generate_report_summary(grounding: dict) -> str:
    """Return executive-summary prose for the given audience-filtered grounding.

    Returns an empty string if the provider is unavailable or errors — generation
    of the Report itself must not fail because the summary could not be written.
    """
    try:
        provider = get_report_summary_provider()
        return provider.generate_report_summary(grounding) or ""
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("generate_report_summary: LLM call failed: %s", exc)
        return ""
