# The incident assistant works manual tasks — researches and records findings, but never executes or closes them

Issue [#457](https://github.com/ReyhZhao/Vels.online/issues/457) asked the incident assistant to see the linked task template, fix it if wrong, and "handle the tasks ... by researching or executing what's needed and updating the tasks with relevant information before closing." A task is one of three types — `manual` (an investigative checklist step), `automated` (launches a Semaphore/Ansible job), or `wazuh_response` (fires a Wazuh active response, e.g. isolate a host / block an IP). This ADR draws the autonomy boundary for that capability **within** the risk-graded contract of [ADR-0012](0012-incident-assistant-relaxed-action-authority.md); it does not supersede it.

## Decision

- **Manual tasks only.** The assistant works only `manual` tasks: it researches each (existing web search / app-lookup tools) and records its findings. It **never executes `automated` or `wazuh_response` tasks** — those are externally visible and touch the customer's live infrastructure, which ADR-0012 puts firmly on the *propose* side. If such a task should run, the assistant may recommend it in prose; the SOC member runs it through the existing staff-only `TaskRunView`.
- **Findings are a task-scoped internal comment.** A new auto-execute tool, `add_task_comment(task_id, text)`, creates a `Comment` with the `task` FK set and `is_internal=True` — reusing the same path as the existing task-comment endpoint and the `ai_task_summary` comments already posted for automated tasks. It is restricted to `manual` tasks belonging to the bound incident, joins `AUTO_EXECUTE_ACTIONS`, and records an assistant-initiated (autonomous) timeline event like the other auto tools. It is a dedicated tool rather than an `add_internal_comment` overload, per ADR-0011's preference for tight single-purpose schemas on the Ollama runtime.
- **The assistant never closes a task.** Completing a task asserts "this work is done" — a judgement that stays the SOC member's, who closes it in the existing task UI after reading the findings. No `complete_task` proposal type is added in v1.
- **Seeing the template is grounding, not a tool.** Per ADR-0011 (cheap, always-relevant context is precomputed), the incident grounding is enriched with each task's `id`, `description`, and `task_type`, plus the applied template name(s). This satisfies "see the current linked template" with no new read tool.
- **Changing the template stays a proposal.** Re-templating spawns/cancels a batch of tasks; it remains the existing `apply_task_template` proposal. The assistant recommends the correct template; the human confirms.
- **Synchronous, opportunistic, report-and-continue.** The endpoint stays blocking under ADR-0011's caps (≈5 iterations, 60s deadline, 8 auto-actions/turn); async is still deferred. A turn makes *progress* rather than guaranteeing completion: the assistant works what fits the budget (batching findings-writes within one iteration), then reports what it did and what remains so the analyst can say "continue."

## Considered Options

- **Manual-only, comment findings, propose-nothing-new (chosen)** — smallest surface that satisfies the issue; stays inside ADR-0012's boundary; reuses existing comment, template, and contact-message paths.
- **Also execute automated/Wazuh-response tasks** — rejected; autonomously isolating a host or blocking an IP is the highest-consequence action in the system and reverses the human-in-the-loop principle for exactly the case it exists to protect.
- **Auto-close tasks once findings are recorded** — rejected; closing is a completion judgement, and a shallow research pass silently dropping a checklist item is the failure mode to avoid. A `complete_task` one-click proposal is the obvious fast-follow if re-finding the task in the UI proves annoying.
- **A dedicated `Task.findings` field instead of a comment** — cleaner separation, but heavier (migration + serializer + UI) and out of step with the existing task-comment convention; the analyst already reads task comments where the close control lives.
- **Async/background task-working** — would lift the budget ceiling, but ADR-0011 defers async to v2; premature here.

## Consequences

- The auto-execute set grows by one action (`add_task_comment`); the action classifier and the audit story extend naturally, no new event type beyond the existing autonomous marker + `comment_added`.
- A template of many deep-research tasks will not finish in one turn; the UX is explicitly progress-plus-continue, not fire-and-forget. If analysts find this tedious, the levers are (a) raise the synchronous caps, or (b) bring forward ADR-0011's deferred async/streaming.
- The boundary is now: **manual-task findings are auto; running any task and closing any task are not.** Classifying future task-related actions follows ADR-0012's two axes unchanged.
- "See the linked template" relies on grounding enrichment, so it is always present and cannot be widened by the client — consistent with the recomputed-server-side invariant.
