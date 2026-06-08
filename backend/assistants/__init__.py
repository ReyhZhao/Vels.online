"""Shared, provider-agnostic agentic tool-calling loop for the LLM assistants.

See ADR-0011 (agentic tool-calling loop) and ADR-0012 (relaxed incident-assistant
action authority). This package is deliberately not a Django app — it holds plain
modules (orchestrator, tool types, PAP egress guard) reused by both the incident
assistant (`incidents`) and the rule-draft assistant (`correlations`).
"""
