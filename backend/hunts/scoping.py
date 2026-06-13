"""Scoping-phase tools (ADR-0018).

`propose_hunt_plan` is the model's structured readiness signal during Scoping: it
records the agreed hunt plan (the durable "shared understanding") so the UI can render a
plan card and emphasise the human-only "Begin hunt" gate. It is present only in the
Scoping toolset, commits no Findings, and never starts the search itself.

Like the lens findings sink, the plan is captured through an injected callback and
persisted on the main thread afterwards — the tool runs inside the orchestrator's
per-tool worker thread, where a direct DB write would lock SQLite.
"""
from assistants.tools import ToolResult, ToolSpec


def _coerce_org_ids(raw):
    out = []
    for o in raw or []:
        if isinstance(o, bool):
            continue
        if isinstance(o, int):
            out.append(o)
        elif isinstance(o, str) and o.strip().isdigit():
            out.append(int(o.strip()))
    return out


def build_propose_hunt_plan_tool(hunt, record_plan=None) -> ToolSpec:
    """A ToolSpec for the model's proposed hunt plan.

    `record_plan(plan)` is invoked with the validated plan dict; the caller persists it
    on the main thread (see hunts.orchestration). When omitted the tool only validates
    and echoes the plan back to the model.
    """

    def executor(args):
        args = args or {}
        refined_question = (args.get("refined_question") or "").strip()
        if not refined_question:
            return ToolResult(error="refined_question is required", summary="bad args")

        hypotheses = args.get("hypotheses") or []
        planned_lenses = args.get("planned_lenses") or []
        suggested_scope = args.get("suggested_scope") or {}
        if not isinstance(hypotheses, list) or not isinstance(planned_lenses, list):
            return ToolResult(error="hypotheses and planned_lenses must be arrays", summary="bad args")
        if not isinstance(suggested_scope, dict):
            return ToolResult(error="suggested_scope must be an object", summary="bad args")

        plan = {
            "refined_question": refined_question,
            "hypotheses": [str(h) for h in hypotheses],
            "planned_lenses": [str(lens) for lens in planned_lenses],
            "suggested_scope": {
                "all_orgs": bool(suggested_scope.get("all_orgs", hunt.scope_all_orgs)),
                "org_ids": _coerce_org_ids(suggested_scope.get("org_ids")),
                "lookback_days": int(suggested_scope.get("lookback_days") or hunt.lookback_days),
            },
        }
        # Hand the plan to the caller's sink (persisted on the main thread). The
        # orchestrator also emits a `tool` event for this call, which the UI keys off.
        if record_plan:
            record_plan(plan)
        return ToolResult(
            content=plan,
            summary=f"hunt plan proposed ({len(plan['planned_lenses'])} lens(es))",
            count=len(plan["planned_lenses"]),
        )

    return ToolSpec(
        name="propose_hunt_plan",
        description=(
            "Signal that you understand the hunt well enough to start, by proposing a "
            "structured plan for the staff member to approve. Provide the refined question, "
            "your hypotheses, the lenses you plan to run, and a suggested scope (all_orgs, "
            "org_ids, lookback_days). This does NOT start the hunt — only the staff member's "
            "'Begin hunt' action does. Call it when ready, then hand back to the human."
        ),
        parameters={
            "type": "object",
            "properties": {
                "refined_question": {"type": "string", "description": "The sharpened question to hunt."},
                "hypotheses": {"type": "array", "items": {"type": "string"}},
                "planned_lenses": {"type": "array", "items": {"type": "string"}},
                "suggested_scope": {
                    "type": "object",
                    "properties": {
                        "all_orgs": {"type": "boolean"},
                        "org_ids": {"type": "array", "items": {"type": "integer"}},
                        "lookback_days": {"type": "integer"},
                    },
                },
            },
            "required": ["refined_question"],
        },
        executor=executor,
    )
