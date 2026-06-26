# Incident Response

The full incident lifecycle and the people and AI that work it: [Incident Management](#incident-management), [Incident Presence](#incident-presence), [On-Call Scheduling](#on-call-scheduling), [AI-Powered Triage](#ai-powered-triage), [IOC Enrichment](#ioc-enrichment), the [Incident Assistant](#incident-assistant), [Threat Hunting](#threat-hunting), [Incident Reports](#incident-reports), [Inbound Phishing Ingestion](#inbound-phishing-ingestion), and [Incident Contacts](#incident-contacts).

See also: [Architecture overview](../architecture.md).

---

## Incident Management

A full lifecycle for security incidents, from detection to closure.

- **Multi-source ingestion** — incidents are created from Wazuh alerts, phishing emails, vulnerability scans, agent findings, or manually by analysts.
- **Severity tiers** — Critical · High · Medium · Low · Info, with SLA tracking displayed in the incident list. Severity auto-escalates when a new linked alert has a higher severity than the current incident.
- **Structured playbooks** — subject-based task templates automatically apply the right checklist (phishing, malware, vulnerability, etc.) when an incident is created.
- **Auto-assignment** — claiming an incident via "Start Work" automatically assigns it to you; the incident subject is also auto-populated from the LLM triage recommendation when one arrives.
- **Immutable audit trail** — every state change, comment, delegation, attachment, and alert link is timestamped in a timeline for complete accountability.
- **Collapsed bulk alert-link events** — when many alerts link to an incident at once (e.g. a Scheduled Search Rule or Threat Hunt materialising dozens of Findings), the timeline coalesces them into a single "*N* alerts linked" entry instead of one row per alert, keeping the timeline readable.
- **Linked-alert drill-down** — click any alert in the Linked Alerts tab to open its full detail (raw event, ECS entity envelope, enrichment) in place, and filter the linked-alerts list with the same controls as the main `/alerts` inbox.
- **One-click Mark Resolved** — resolving an incident closes it in a single action rather than a two-step state change.
- **Extended close flow** — close incidents as resolved, as a **false positive**, as **no impact** (a true positive that caused no harm — distinct from a false positive), or as a **duplicate** linked to a canonical incident; a searchable combobox makes finding the canonical incident fast even across large lists.
- **`pending_closure` state** — incidents the Triage Agent has contained land in a reopenable `pending_closure` state awaiting human ratification, kept separate from the active work queue (see [AI-Powered Triage](#ai-powered-triage)).
- **Auto-closure** — incidents older than 7 days in `new`, `triaged`, or `resolved` state are automatically closed, keeping the active queue clean.
- **Delegation and transfers** — analysts can temporarily hand off work to teammates and receive it back, maintaining a clear chain of responsibility.
- **Move incident between organisations** — staff can reassign an incident to a different organisation when it lands in the wrong tenant's queue, correcting routing errors without recreating the incident.
- **TLP/PAP-aware communications** — sensitive findings are gated by classification level so customers see exactly what they are entitled to see.
- **Multi-select state filter** — the incident list state filter is a multi-select that defaults to every state *except* closed, so the active queue is front-and-centre without hiding any one stage.
- **Org-aware incident table** — the incident list shows the owning organisation column (replacing the TLP column) so MSSP staff can see at a glance which tenant each incident belongs to.
- **Persistent filter & sort preferences** — each user's chosen filters and sort order are remembered across sessions.
- **Incident Trend chart** — a collapsible, persistent panel above the incident list plots incidents over time bucketed by **Subject**, with a range toggle (e.g. 7/30/90 days) so analysts can see at a glance which categories of incident are rising. Clicking a Subject series drills the list down to it (including a `subject=none` bucket for untriaged incidents) via a removable filter chip, tying the analytics view back to the working queue. The panel is mobile-aware and remembers its open/closed state.
- **Route-backed asset links** — linking an ingress [Route](estate-management.md#app-ingress-reverse-proxy--waf) to an incident automatically pulls in the host asset behind it, so the incident carries the real backend even when analysts reason in terms of the public service.
- **Tab counters** — incident detail tabs (Tasks, Contacts, IOCs, Assets, Attachments, Linked Alerts) show item counts at a glance.
- **Smart page refresh** — the incident detail page detects when new data is available (triage result, new alert link, comment) and prompts for a reload without forcing a full refresh.
- **Multi-organisation support** — each organisation has its own incident queue, team, and settings; admins can manage all orgs from one account.

---

## Incident Presence

See who else is on an incident in real time and avoid colliding on the same work. Presence is a lightweight collaboration overlay on the incident detail view, streamed over Server-Sent Events and backed by an ephemeral cache registry (no database writes).

- **Live roster** — each open incident shows who is currently present and what each person is doing: passively **viewing**, **working** a specific task, or **editing** a specific comment. The roster is a full snapshot refreshed every second or two; closing or backgrounding the tab drops you off automatically.
- **AI actors in the roster** — the incident's AI agents appear as first-class roster members too (e.g. "🤖 Incident Assistant", a Triage Agent re-run), sourced from the agentic orchestrator rather than a browser connection and attributed to the analyst who invoked them, so live AI work is visible alongside human work.
- **Soft comment-edit lock** — because a comment body is last-write-wins and genuinely clobberable, the first analyst to edit an existing comment holds a soft lock; others get a read-only editor attributed to the holder. The lock self-releases when the tab closes and auto-releases after a few idle minutes, so it prevents the common accidental overwrite without ever deadlocking a comment. Composing a *new* comment is never locked, and working a task is advisory only (two analysts may focus the same task — presence informs the collision, it doesn't prevent it).
- **Fails open** — presence is a non-critical overlay: if the cache is unavailable it silently no-ops and the page behaves exactly as it did before, and the lock fails open rather than blocking edits.
- **Staff-only** — customer org members can open an incident but neither see nor emit presence.

---

## On-Call Scheduling

Manage 24/7 analyst coverage and automatically route post-triage incidents to the analyst on duty.

- **Shift blocks** — admins define named time blocks (e.g. Day / Evening / Night) that must collectively tile 00:00–24:00 without gaps or overlaps; the system validates full coverage before the template can be saved.
- **Repeating weekly rotation template** — assign a staff analyst to each day-of-week × shift-block slot; the template repeats indefinitely until explicitly changed, requiring no weekly manual input.
- **Shift overrides** — any analyst can initiate a shift swap (hand off their own upcoming shift) or offer to cover a colleague's shift; the receiving analyst accepts or declines via notification. A pending override does not affect the resolver until accepted, so there is never a coverage gap during the handoff process.
- **Hand-off now** — the active on-call analyst can transfer responsibility immediately from the calendar page without pre-planning a swap.
- **Pending requests panel** — outstanding swap and cover-offer requests are surfaced in a dedicated panel so recipients can action them without hunting through the calendar.
- **Post-triage incident routing** — after AI triage promotes an incident to `triaged`, the routing service automatically assigns it to the current on-call analyst. The routing mode is controlled via the `ONCALL_ROUTING` env var: `always` routes every triaged incident; `llm_guided` routes only when the triage recommendation is `escalate` or `assign_to_analyst`. If no on-call analyst is found, a system alert is sent to all staff.
- **Coverage gap detection** — the month calendar view renders days with no assigned analyst in red with a GAP badge so admins can fix gaps before they go live.
- **Timezone-aware display** — each staff analyst sets their local timezone in their profile (default: Europe/Amsterdam); all shift times in the UI are converted to the viewer's local timezone.
- **Compact on-call widget** — the incident list header shows who is currently on-call and when their shift ends, so analysts always know who owns incoming work without leaving their main workspace.
- **shift_swap notifications** — swap requests and cover offers trigger notifications via email, in-app, or push. At least one channel must remain enabled per analyst so coverage-critical requests are never missed.

---

## AI-Powered Triage

Reduce analyst workload on repetitive alert screening. Triage runs in **two stages** — a cheap classify that fires on every incident, and a confidence-gated agentic **Triage Agent** that works the playbook unattended when the model is sure.

**Classify (always runs).** A single LLM call on every new incident.

- Analyses the incident (title, description, raw Wazuh event, linked assets, IOCs and their enrichment data) and returns a structured assessment: recommended severity, subject, 2–3 sentence summary, primary and secondary suggested actions, and **two** confidence scores — a **false-positive** confidence and a distinct **disposition** confidence (how sure it is about *what kind* of incident this is). The two are independent: an incident can be clearly-not-junk (low FP) yet still ambiguous to classify (low disposition).
- High false-positive confidence (≥ the org's `triage_fp_threshold`) auto-closes the incident as a false positive; everything else transitions to `triaged` and routes to on-call.
- **Pluggable providers** — ships with Google Gemini and Ollama backends; swap via a single environment variable (`TRIAGE_LLM_PROVIDER`).
- **Per-org custom context** — admins can add organisation-specific prompt context (e.g. known safe IPs, environment notes) to sharpen triage accuracy for their estate.
- **Customisable LLM prompt** — org admins can edit the base triage prompt directly from the settings page to tune the model's behaviour for their environment.
- Triage results surface in the incident timeline as a labelled AI comment with recommended actions shown inline; analysts accept or override with one click.
- Triage status is prominently displayed on the incident detail page; a smart-reload banner appears the moment a triage result arrives.

**Triage Agent (gated, unattended).** A background agentic phase that runs **only** when the disposition confidence clears the org's `triage_work_threshold` *and* a subject (hence a playbook) matched. It reuses the same agentic tool-calling loop as the Incident Assistant and Hunt, but with no human present, so its boundary is drawn on **confidence** rather than a confirmation click.

- **Works the playbook for you** — applies the matched subject's task template(s), researches each manual task and records its findings as task-scoped internal comments, and sets severity/subject/state, so the routed analyst inherits a part-worked incident instead of a blank one.
- **Acts on live infra within the gate** — runs `automated` (Semaphore) runbooks unconditionally, and fires a `wazuh_response` (e.g. host-isolation / IP-block) **only** if that catalog entry is **autonomous-response approved** (a default-off, global-per-response `autonomous_triage_approved` flag, distinct from the human-facing "requires confirmation"). It can also notify the incident's contacts and escalate.
- **Never closes the incident, never creates exceptions** — closing a worked incident stays the human's ratification. On finishing it routes to on-call and lands the incident in `in_progress` (work remains) or the new **`pending_closure`** state (threat contained, only sign-off left).
- **Once per incident, fully audited** — guarded by a durable marker so retries and later-linking alerts never re-enter the work phase; every autonomous action is recorded on the timeline as an assistant-initiated (autonomous) event, and the run posts an AI-triage summary comment carrying its tool-trace and a "what remains" note. The staff-only manual triage button is the deliberate human re-trigger.
- **Background, not streamed** — it runs as a Celery job with hunt-style relaxed caps (no live SSE stream, since nobody is watching at triage time).
- **Two tuning knobs per org** — `triage_fp_threshold` (auto-close FPs) and `triage_work_threshold` (unlock the agent) are the only levers operators tune; spend rises only on the gated high-confidence path.

---

## IOC Enrichment

Automatically assess every indicator of compromise at incident creation time.

- **IP addresses** — queried against AbuseIPDB; results include abuse confidence score, total reports, country, and usage type.
- **Domains and URLs** — queried against VirusTotal; malicious/suspicious vote counts surfaced inline.
- **Email addresses** — extracted from phishing emails and displayed as a dedicated IOC kind in the IOC tab.
- **Owned-asset deduplication** — IPs that belong to assets already registered in the organisation's estate are skipped at ingestion time so the IOC tab stays focused on external indicators. Internal IP ranges and the organisation's own owned domains are likewise excluded from automatic extraction so enrichment effort goes to genuinely external indicators.
- **Analyst-curated IOCs** — analysts can add, edit, and remove IOCs on an incident by hand, correcting a mis-parsed indicator or adding one the automatic extraction missed; manually added IOCs are enriched the same way as extracted ones.
- Enrichment data is available to the AI triage pipeline immediately, improving the quality of automated assessments.
- Enriched IOCs display threat intelligence details in the IOC tab without requiring analysts to leave the platform.

---

## Incident Assistant

An interactive AI panel embedded in the incident detail page for conversational investigation and action. It runs an **agentic tool-calling loop**: within a single turn the model can call tools to fetch what it needs, take a bounded set of safe actions, and then answer — keeping a human in the loop for anything consequential.

- **Investigate with read tools** — the assistant can look up related incidents, query other alerts in the org, and inspect assets on demand, so an analyst can spot a wider campaign or check whether an indicator appears elsewhere without leaving the drawer.
- **Host inventory lookup** — a `host_inventory` tool lists a single host's installed software, services, or running processes (read from the Wazuh IT Hygiene Inventory state indices), scoped to the incident's organisation, so the assistant can answer "what is installed/running on this host?" while investigating.
- **Internet-facing exposure awareness** — the assistant can see whether a linked host presents external attack surface and *how* — the full per-exposure list with its protection trait (behind the WAF vs. raw direct-NAT) — so it reasons about an attacker's actual reachable surface rather than guessing (see [Internet-facing exposures](estate-management.md#fleet--asset-management)).
- **Live web search** — the assistant can search the internet for threat intelligence on an IOC or CVE and cite where its findings came from. Web search uses each provider's native capability (Ollama Cloud's web-search API as the primary runtime, Gemini's Google Search grounding as backup); a self-hosted Ollama with no cloud key degrades gracefully to app-data-only rather than erroring.
- **PAP-gated egress** — internet lookups obey the incident's PAP. At PAP white/green/amber the model may search incident-specific indicators; at PAP:RED an egress guard blocks any query containing the incident's own indicators (IOC values, asset/agent names, IPs, linked usernames) while still allowing generic research, so sensitive specifics never leave the boundary.
- **Auto-execute safe actions** — internal, reversible, non-lifecycle actions run by themselves: add an internal comment, self-assign the incident, add a tag, or link a known asset. Each is performed through the same mutation service as a manual edit and recorded on the timeline as an assistant-initiated (autonomous) event.
- **Propose-and-confirm for consequential changes** — anything externally visible or lifecycle/severity/disclosure-affecting — state transitions, severity/TLP/PAP/subject/assignee edits, applying a task template, messaging a contact, creating an exception, closing — is only ever *proposed*, with one-click human confirmation.
- **Works manual tasks** — the assistant can see the incident's task list and applied task template, research each manual task (web search + app lookups), and record its findings as a task-scoped internal (staff-only) comment for the analyst to review. It works several tasks per turn within its time budget and reports which it completed and which remain, so the analyst can simply say "continue." It never closes a task, never runs `automated` (Semaphore) or `wazuh_response` tasks — recommending those in prose for the analyst to run through the existing controls — and proposes (never silently applies) a corrected task template.
- **Live streaming over SSE** — each turn streams its progress to the drawer over Server-Sent Events (phase, tool, action, result events), so the analyst watches the assistant work step-by-step instead of waiting on a spinner, and a dropped connection can reconnect.
- **Tool trace** — each turn surfaces a trace of what the assistant searched and looked up, plus web citations, so analysts can trust and verify its reasoning. Auto-executed action notices are visually distinguished from proposed actions that still show confirm buttons.
- **Bounded execution** — every turn is capped by max iterations, a per-tool timeout, an overall deadline, and a per-turn auto-action limit, so a runaway loop can never hang a request.
- **Org-scoped lookups** — app lookups reuse the same permission predicates as the REST API and default to the incident's organisation; staff may deliberately widen a lookup across organisations to correlate a cross-tenant threat.
- **Incident context aware** — the assistant is grounded in the full incident context: title, description, severity, state, linked alerts, IOCs, assets, tasks, and timeline. Responses are relevant to the specific incident rather than generic.
- **Ollama and Gemini support** — the incident assistant respects the same pluggable LLM provider configuration (`ASSISTANT_LLM_PROVIDER`) as the rest of the platform, working with Ollama Cloud models as well as Google Gemini (Gemini 3, required for combining web-search grounding with function tools).
- **Grouped residual alert analysis** — the Ollama triage provider can group residual (unlinked) alerts and return a structured analysis, surfacing clusters of related signals the static engine did not catch.

---

## Threat Hunting

Drive an LLM-assisted, cross-org investigation *from a question or a report* — not bound to an existing incident. Where the Incident Assistant reacts to an incident we already have, a **Hunt** is **incident-producing**: a staff member asks "are we exposed to this campaign?" and the platform ranges over the whole Wazuh fleet to find out. Staff-only; every Hunt is the audit record for the cross-tenant access it performs.

- **Seed from a question or a report URL** — start a Hunt from a free-text hunch or by pasting a link to a malware/threat writeup. URL seeds are fetched server-side and the IOCs and hunting intent are extracted for you.
- **Interactive Scoping phase** — every Hunt opens in a **Scoping** dialogue: the model grills the staff member (and the staff member corrects it) to reach a shared understanding *before* any evidence-committing search runs. During Scoping the model has the full toolset (web search **and** every Wazuh lens) so its questions are grounded in current threat-intel and the real fleet — but its lens calls commit **no Findings**.
- **Structured hunt plan + human "Begin hunt" gate** — when the model judges it has enough, it surfaces a plan card (refined question, hypotheses, planned lenses, suggested scope/lookback). The transition into the authoritative search is fired only by an explicit human **Begin hunt** action — never by the model — and the human can adjust scope/lookback at the gate. Begin is available from the first moment, so a known hunt can skip the dialogue and one-shot as before.
- **IOC sweep + behavioral hunting** — composable, single-purpose Wazuh *lenses* let the Hunt sweep every managed agent for a hash/IP/domain/filename, or run open-ended pattern hunts (top rules, event histogram, top values, agent activity, processes/ports) for activity no one could name in advance.
- **General-query lens** — a structured `search_events` lens lets the model compose a *novel* aggregation the fixed lenses can't express ("failed logins grouped by source IP then by user," "distinct destination ports per source IP over time"): a list of validated `field/operator/value` filters plus a bounded aggregation spec (`group_by` ≤2 nested terms, a `count`/`cardinality`/`sum`/`avg` metric, optional time histogram). The model never writes OpenSearch DSL — every field is type-validated against the live mapping and every aggregation choice is enum-constrained, so the lens is injection-safe by construction; a companion `describe_fields` tool lets the model discover populated fields/types on demand instead of dumping the ~3000-field mapping into the prompt. It explores only (commits no Findings), stays per-org by construction, and is gated to capable cloud models — a self-hosted Hunt silently keeps the fixed lenses, the same way it degrades web search.
- **IT Hygiene Inventory hunting** — an `inventory_search` lens sweeps the fleet's installed software / services / running processes (read from the Wazuh IT Hygiene Inventory state indices) to answer "which hosts anywhere run X?", returning matching hosts and counts. Because a bare software/service/process name is usually benign, matches are *not* auto-recorded; the model judges, then logs the compromised one with a deliberate `record_inventory_finding`, which rides the normal propose-and-confirm → materialise bridge to an incident.
- **Internet-facing asset briefing** — the in-scope asset inventory the model is briefed with flags which hosts are internet-facing and how they are exposed (WAF-protected ingress route vs. raw direct-NAT), so the Hunt can prioritise externally-reachable surface.
- **Cross-org by default, tenant-isolated by construction** — a Hunt reads across all tenants by default (configurable to selected orgs) over a staff-selectable lookback window. Every query is **fanned out per tenant and never joined across tenants**; Findings and any spawned incidents are always partitioned by org.
- **Shared Infrastructure hunting** — a dedicated, non-tenant **Infrastructure organisation** lets an all-orgs hunt reach perimeter telemetry that belongs to no agent (the firewall / reverse proxy logging as the Wazuh manager, `agent.id = "000"`). Agent-less events surface as Infrastructure findings and confirm into an Incident that lives in the Infrastructure org, so a real tenant's queue never holds mis-attributed perimeter events. Infrastructure is selectable on its own in the scope picker and never leaks into other org dropdowns.
- **Live web-search enrichment** — within the loop the Hunt can search the public internet for threat intelligence on an indicator or campaign and cite its sources.
- **Propose-and-confirm incidents, per org** — when a Hunt finds something worth investigating it groups **Findings by affected org** and offers **one proposed Incident per org**. It never auto-creates incidents — a human always confirms what enters a customer's queue. Confirming **materialises** the matched raw Wazuh documents as Alerts (`source_kind = threat_hunt`) linked to the new Incident, so it carries its evidence through the normal IOC-enrichment and triage pipeline.
- **Rich incident hand-off** — a confirmed Hunt finding produces a fully-formed incident: the indicators it matched on (IPs, hashes, domains, filenames) are extracted into linked IOCs rather than buried in prose, and the description carries a compact-but-complete summary of the Hunt's findings instead of a sparse placeholder.
- **Streamed, resumable, audited** — each turn runs as a Celery background job that writes onto the Hunt's persisted event log; the SSE endpoint tails/replays that log, so progress streams live, survives a dropped connection, and can be reconnected. A Hunt is persisted and resumable: step away mid-Scoping or mid-run and come back. Follow-up turns let you dig deeper, and the questions you ask persist in the transcript as chat bubbles so you can track what has been done.
- **Bounded execution** — every turn is capped by max iterations, per-tool timeout, an overall wall-clock deadline, and a per-lens fan-out cap (max orgs/agents per query), so one Hunt can never saturate workers or run forever. Cancel abandons the whole Hunt explicitly, independent of the transport.
- **SSRF-guarded report fetcher** — the URL seed refuses private/link-local/loopback/metadata addresses and disallowed schemes, caps response size, and will not follow cross-host redirects into internal space; fetched content is treated as untrusted, prompt-injection-aware data rather than instructions.
- **Recommend-only on live infra** — like the Incident Assistant, a Hunt auto-executes only its own internal, reversible artifacts (notes/findings). It never runs `automated` (Semaphore) or `wazuh_response` actions — it recommends them in prose for an analyst to run through the existing controls.
- **Hunt console** — a staff-only **Threat Hunting** top-level view lists past and in-progress Hunts (owner, seed, scope, status, findings count, spawned incidents) with **search, sorting, and filtering**; admins can **delete** (including bulk-delete) completed or incomplete Hunts to clean up the list.
- **Hunt notifications** — the Hunt owner is notified when a long-running Hunt completes or surfaces proposed incidents, so staff don't have to babysit the console.

---

## Incident Reports

Generate a shareable, exportable document about an incident — for a customer or an internal stakeholder — without leaking the incident's internal material. A **Report** is an **immutable, point-in-time snapshot** (a stored PDF): generating one freezes the incident's then-current state so it is always answerable exactly what was shared, and when. The incident changing later never alters an existing Report — you generate a new one.

- **SOC-authored section-catalog templates** — a **Report Template** is an ordered selection from a fixed, server-defined catalog of sections (Executive Summary, Incident Details, Timeline, IOCs, Actions Taken, Recommendations, Asset Impact) plus free-text intro/outro blocks. Authors *choose and order* sections and fill the free text; they never hand-write markup that pulls arbitrary incident fields, so a template cannot be authored that renders internal content.
- **Audience visibility floor — leak-safe by construction** — Audience is a property of the template. A `customer` template always renders through the exact floor an organisation member would see for that incident (non-internal comments/events only, nothing at TLP:RED, no comments/events at TLP:AMBER) **regardless of which staff member clicks generate**, so a staff-generated customer report cannot leak internal AI triage traces, internal comments, or raw exposure detail. An `internal` template renders full fidelity for SOC management and the post-incident record.
- **Two disclosure rules beyond the floor** — the **IOCs** section respects a **PAP ceiling** (indicators render only at PAP:WHITE/GREEN, suppressed at AMBER/RED), and the **Asset Impact** section lists linked asset names/roles only and omits all exposure specifics, so a customer report never doubles as an exposure map of the customer's own hosts.
- **LLM executive summary on filtered grounding** — the Executive Summary is generated by the LLM at render time, grounded **only** on the audience-filtered content (not the full staff-side incident grounding), then frozen into the snapshot like every other section, so a customer summary cannot mention internal findings.
- **Human-ratified generation** — an analyst generates a Report from the incident detail view at any incident state (an interim update is valid); the [Incident Assistant](#incident-assistant) may *propose* generating one for one-click confirmation. The unattended Triage Agent never generates Reports — a customer-facing deliverable stays a human action.
- **Delivery** — every Report is staff-downloadable; a `customer`-Audience Report additionally surfaces in the organisation member's own incident view for self-service download. Editing or deleting a template never touches Reports already generated — corrections are new snapshots, and superseded Reports are retained as the audit trail.

---

## Inbound Phishing Ingestion

Turn phishing reports into incidents with zero analyst effort.

- Forward any suspected phishing email to `soc@vels.online`; the platform creates an incident automatically.
- Parses forwarded and attached `.eml` files; extracts raw email body as the incident description.
- Extracts URLs, domains, sender addresses, and email addresses as IOCs and enriches them immediately (see [IOC Enrichment](#ioc-enrichment)).
- LLM triage annotates phishing incidents with email-specific context (sender reputation, URL risk, attachment analysis).
- **Contacts allow list** — known-safe senders (internal staff and registered contacts) are excluded from phishing incident creation to prevent analyst noise.
- **Auto-link forwarder as contact** — the user who forwarded the phishing email is automatically added as an `IncidentContact` on the created incident so they can be updated as the investigation progresses.
- **Forwarder as incident creator** — if the forwarding address matches a platform user record, that user is set as the incident's `created_by` so ownership is accurate rather than attributed to the IMAP poller.
- **Closure contact notifications** — when a phishing incident is closed, a notification email is sent to linked contacts. If the phishing email address can be identified as a drop address, a dedicated drop-confirmation email is sent.

---

## Incident Contacts

Link employees and asset owners to incidents for structured communication.

- **Contact directory** — per-organisation directory of natural persons (employees, contractors, asset owners) with name, email, job title, and department.
- **Org-scoped contact list** — the contacts list filters to the currently selected organisation by default (matching the asset list), with a toggle to show contacts across all orgs; when showing all, each contact's organisation is displayed in the table.
- **Asset ownership** — assign assets to contacts; when an incident is created and an asset is linked, the owner contact is automatically associated with the incident.
- **In-platform Q&A** — analysts can message a contact directly from an incident (role: `notified` or `questioned`); the platform sends the email and ingests replies back into the incident timeline via IMAP polling.
- **Threaded messaging** — outbound questions and inbound replies are displayed as a conversation thread within the incident detail.
