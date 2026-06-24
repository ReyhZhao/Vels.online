"""AI presence bridge (PRD #605 slice #610, ADR-0028 + ADR-0014).

Adapts the shared agentic orchestrator's ``on_event`` step boundaries into Incident
Presence registry writes for a synthetic ``actor_kind=ai`` roster member, so staff
watching an incident see the Triage Agent re-run / Incident Assistant working it
live. AI actors hold no browser connection: presence is registered on run start,
updated per step, and **dropped in ``finally``** (TTL is the backstop on crash).

AI actors never contend for the comment lock — they only ever *create* new comments.
"""
import logging
import uuid
from contextlib import contextmanager

from . import presence

logger = logging.getLogger(__name__)

ASSISTANT_NAME = "Incident Assistant"
TRIAGE_AGENT_NAME = "Triage Agent"


class AIPresence:
    """Handle for one AI actor's presence on an incident. All ops fail open."""

    def __init__(self, incident_id, display_name, run_by=None):
        self.incident_id = incident_id
        self.actor_key = f"ai:{uuid.uuid4().hex}"
        self.display_name = display_name
        self.run_by = run_by

    def _write(self, activity, target=None):
        presence.set_activity(
            self.incident_id, self.actor_key, activity, target,
            display_name=self.display_name, actor_kind=presence.ACTOR_AI,
            run_by=self.run_by,
        )

    def start(self):
        self._write(presence.ACTIVITY_WORKING)

    def on_event(self, event: dict):
        """Map an orchestrator step event to a coarse activity update."""
        try:
            etype = (event or {}).get("type")
            if etype in ("phase", "tool", "action"):
                # Coarse grain: the agent is working the incident. A task id is not
                # generally available from these events, so target stays None.
                self._write(presence.ACTIVITY_WORKING)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("AIPresence.on_event failed: %s", exc)

    def drop(self):
        presence.drop(self.incident_id, self.actor_key)


@contextmanager
def ai_presence(incident_id, display_name, run_by=None):
    """Context manager: register an AI actor, drop it on exit (incl. error)."""
    handle = AIPresence(incident_id, display_name, run_by=run_by)
    try:
        handle.start()
        yield handle
    finally:
        handle.drop()
