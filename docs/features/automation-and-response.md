# Automation & Response

Take action from inside the platform: launch runbooks via [Automations](#automations), fire endpoint remediation with [Wazuh Active Response](#wazuh-active-response), and suppress known-good noise with [Exception Rules](#exception-rules).

---

## Automations

Trigger runbook-style workflows without leaving the platform.

- Automations map to Semaphore CI/CD templates; analysts can launch them from incident tasks with optional variable overrides.
- **Incident var mappings** — each automation can declare a YAML mapping from Semaphore playbook variable names to incident data sources (linked assets, IOCs, core incident fields). Variables are resolved automatically at run time — no manual copy-paste.
- **Pre-run preview modal** — before launching an automation, analysts see a preview of all resolved variables and can edit any value before confirming, so they can verify and adjust data without leaving the platform.
- **Auto-assign on start** — starting an automation task automatically assigns it to the analyst who clicked Start, creating a clear chain of responsibility.
- Task templates can be pre-wired to an automation so the right runbook fires automatically when a checklist item is started.
- In-progress automation status is tracked and surfaced on incident tasks in real time.
- **LLM-summarised output** — when an automation run completes, the platform feeds the raw output through the LLM and posts a concise summary as a task comment alongside the full output, reducing the need to parse verbose CI logs.
- **Wazuh response task type** — in addition to Semaphore automations, tasks can be of type `wazuh_response` to dispatch a Wazuh active response command directly from an incident checklist item (see [Wazuh Active Response](#wazuh-active-response) below).

---

## Wazuh Active Response

Take direct remediation actions on endpoints from within the platform — no context-switching to the Wazuh management interface.

- **Response catalog** — admins manage a global catalog of Wazuh active response commands (e.g. `firewall-drop`, `host-deny`). Each entry specifies supported OS platforms (`linux`, `windows`, `macos`), a default argument template with `{{incident.field}}` interpolation placeholders, a configurable timeout, and flags for security-overview visibility and destructive-action confirmation.
- **`wazuh_response` incident tasks** — task templates and ad-hoc checklist items can be wired to a catalog entry. The run modal shows an agent multi-picker (filtered to the response's supported platforms), pre-resolved argument values, a timeout field, and — for destructive commands — a required typed confirmation phrase (the agent hostname).
- **Variable interpolation** — `{{incident.id}}`, `{{asset.ip}}`, `{{ioc.ip}}`, `{{ioc.domain}}` and similar placeholders are resolved server-side before the modal opens; unresolvable placeholders remain editable so analysts can fill them in manually.
- **Auto-complete on dispatch** — once the Wazuh API accepts the command, the task is automatically marked done and a system comment is added to the incident timeline recording the command, target agents, arguments, timeout, and the analyst who dispatched it.
- **Security overview fast path** — active agent rows in the `/security` dashboard have a kebab menu showing catalog entries filtered to the agent's OS and flagged for security-overview use. Analysts can optionally link the execution to an existing incident; if linked, a task is created and the incident timeline is updated.
- **Agent response history** — the agent detail page has a dedicated Responses tab listing every `WazuhResponseExecution` for that host: timestamp, response name, executed by, args, timeout, linked incident, and Wazuh API status code.
- All active response executions are fire-and-forget (the Wazuh API queues the command on the agent); the timeline entry reflects dispatch, not confirmed execution.

---

## Exception Rules

Suppress known-good alerts so analysts focus on real threats.

- Create Wazuh exception rules from within the platform with a form-based UI (no XML editing required).
- Rules are assembled into valid Wazuh XML and pushed directly to a GitHub repository via the API; the Wazuh deployment picks them up on its next sync.
- IDs are allocated from a managed pool to avoid collisions; freed IDs are recycled automatically.
- Approval workflow: exceptions require review before the GitHub push is made.
- **Auto-update deployment config** — when a new exception file is pushed, the platform automatically updates the `apps-values.yaml` deployment manifest so the rule is included in the next Wazuh sync without manual config editing.
- **Automatic Wazuh restart** — ten minutes after a rule is pushed the platform triggers a rolling Wazuh manager restart so the new exception takes effect without requiring manual intervention.
