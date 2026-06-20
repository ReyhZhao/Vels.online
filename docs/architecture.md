# Architecture

How data moves through Vels.online — from raw detection to closed incident — and where the code that does it lives. For the domain language behind these concepts, see [`CONTEXT.md`](../CONTEXT.md) and the decision records in [`docs/adr/`](adr/).

---

## How It Works

Everything in Vels.online flows through two stages: detections arrive as **Alerts** and are filtered in the **Alert Ingestion Pipeline**, and the ones that matter become **Incidents** that move through an automated **Incident Lifecycle** — IOC enrichment, two-stage AI triage (a cheap classify plus a confidence-gated **Triage Agent** that works the playbook unattended), on-call routing, and the Incident Assistant — with notifications firing at every meaningful step.

```mermaid
flowchart TD
    %% ---- Entry points ----
    WZ["Wazuh agents"]
    SSR["Scheduled Search Rules<br/>OpenSearch pull"]
    WH["Webhooks / N8N / external"]
    PH["Phishing email<br/>soc@vels.online"]
    VL["Vulnerability scans"]
    HUNT["Threat Hunt<br/>staff cross-org LLM hunt"]
    MAN["Manual analyst entry"]

    %% ---- Alert ingestion pipeline ----
    subgraph PIPE["1 · Alert Ingestion Pipeline"]
        direction TB
        INBOX["Alert inbox · AL-NNN<br/>ECS entity envelope"]
        DUP{"Matches an<br/>open incident?"}
        ROUTE{"Severity routing"}
        WAIT["Hold in inbox<br/>+ asset-threshold promotion"]
        CORR["Correlation engine<br/>legs + rolling window"]
        RESID["LLM residual safety-net"]
        SUGG["Detection Suggestions<br/>analyst review"]
        LINK["Link to existing incident"]

        INBOX --> DUP
        DUP -- "yes" --> LINK
        DUP -- "no" --> ROUTE
        ROUTE -- "low / medium" --> WAIT
        INBOX --> CORR
        INBOX --> RESID --> SUGG
    end

    WZ --> INBOX
    SSR --> INBOX
    WH --> INBOX

    %% ---- Incident lifecycle ----
    subgraph LIFE["2 · Incident Lifecycle"]
        direction TB
        INC["Incident created · INC-NNNN"]
        IOC["IOC extraction + enrichment<br/>AbuseIPDB · VirusTotal"]
        CLASSIFY["AI triage · Classify (always)<br/>severity · subject · summary<br/>FP + disposition confidence"]
        FPCLOSE["Auto-close<br/>false positive"]
        GATE{"Confident +<br/>subject matched?"}
        AGENT["Triage Agent · unattended<br/>apply playbook · work manual tasks<br/>run automated + approved responses<br/>notify contacts · escalate"]
        ONCALL["On-call routing<br/>assign analyst on duty"]
        WORK["Analyst + Incident Assistant<br/>agentic investigate & act"]
        PEND["pending_closure<br/>threat contained · awaiting<br/>human ratification"]
        CLOSE["Resolve / close"]

        INC --> IOC --> CLASSIFY
        CLASSIFY -- "high FP confidence" --> FPCLOSE
        CLASSIFY --> GATE
        GATE -- "yes" --> AGENT --> ONCALL
        GATE -- "no" --> ONCALL
        ONCALL --> WORK --> CLOSE
        AGENT -. "threat contained" .-> PEND --> CLOSE
    end

    %% ---- Pipeline hands off to an incident ----
    ROUTE -- "high / critical" --> INC
    WAIT --> INC
    CORR --> INC
    SUGG -- "accepted" --> INC
    PH --> INC
    VL --> INC
    HUNT -- "confirmed finding<br/>(materialises alerts)" --> INC
    MAN --> INC

    %% ---- Notifications fire throughout ----
    NOTIFY["Notifications<br/>in-app · web push · email"]
    LINK -.-> NOTIFY
    CLASSIFY -.-> NOTIFY
    AGENT -.-> NOTIFY
    ONCALL -.-> NOTIFY
    WORK -.-> NOTIFY
    CLOSE -.-> NOTIFY
```

_Solid arrows show how data moves; dotted arrows show where notifications are sent._

**Walking through it:**

1. **Detections arrive.** Wazuh agents, Scheduled Search Rules (pulled from OpenSearch), webhooks, forwarded phishing email, vulnerability scans, staff-driven Threat Hunts, and manual entry all feed the platform. Push-based detections land in the **Alert inbox** as `AL-NNN` records, each carrying a normalised ECS entity envelope; phishing email, vulnerability scans, confirmed Threat Hunt findings, and manual reports open an incident directly.
2. **The pipeline filters noise.** Each new alert is checked against open incidents — a match **links** in instead of creating a duplicate. Unmatched alerts are routed by severity: **high/critical auto-promote** to a new incident; **low/medium wait** in the inbox until an analyst acts or an asset-threshold promotion fires. In parallel, the **correlation engine** raises an incident when multiple alerts satisfy a rule's legs within its window, and an **LLM residual safety-net** groups leftover signals into **Detection Suggestions** for analyst review.
3. **An incident is created.** However it was raised, the incident enters the same lifecycle: **IOC enrichment** scores indicators against AbuseIPDB and VirusTotal, then the **Classify** phase of triage has the LLM recommend a severity, set the subject, write a summary, suggest actions, and emit two confidence scores (false-positive *and* disposition). High false-positive confidence auto-closes the incident; everything else moves on.
4. **A confident incident gets worked automatically.** When the disposition confidence clears the org's work threshold *and* a subject (hence a playbook) matched, a gated **Triage Agent** runs the shared agentic loop unattended: it applies the playbook, researches and annotates manual tasks, fires `automated` runbooks and pre-approved `wazuh_response` actions, and notifies contacts or escalates. It never closes the incident — it hands off to on-call, landing the incident either back in `in_progress` (work remains) or in **`pending_closure`** (threat contained, only human ratification left). Low-confidence or subject-less incidents skip straight to on-call as before.
5. **It reaches the right analyst.** **On-call routing** assigns the incident to whoever is on duty, who inherits either a blank incident or one the Triage Agent has already part-worked.
6. **The analyst works it — with help.** The **Incident Assistant** runs an agentic loop alongside the analyst: it investigates (related incidents, alerts, assets, host inventory, internet-facing exposure, live web search), auto-executes safe internal actions, works manual tasks, and proposes anything consequential for one-click confirmation — until the incident is resolved or closed.
7. **Notifications keep everyone informed.** In-app, web-push, and email notifications fire on assignment, triage results, autonomous Triage Agent actions, state changes, and closure, so no one has to poll for updates.

For the detail behind each stage, see the [feature docs](features/).

---

## Project Structure

```
.
├── backend/              # Django application
│   ├── alerts/           # Alert ingestion pipeline, inbox, auto-routing, ECS entity envelope
│   ├── incidents/        # Incident lifecycle, tasks, LLM triage
│   ├── assistants/       # Agentic tool-calling loop, providers, web search (shared by incident assistant + hunts)
│   ├── hunts/            # Threat Hunting module: Hunt aggregate, scoping, lenses, SSRF fetcher, finding→incident grouping
│   ├── correlations/     # Correlation Rules, Scheduled Search Rules, Detection Suggestions, rule-author assistant
│   ├── security/         # Organisations (incl. Infrastructure pseudo-org), assets, vulnerabilities, CVE advisories
│   ├── exceptions/       # Wazuh exception rule management
│   ├── ingress/          # BunkerWeb-backed reverse proxy routes
│   ├── automations/      # Semaphore automations + Wazuh active response catalog and executions
│   ├── oncall/           # On-call scheduling, shift blocks, rotation templates, swap service, routing
│   ├── contacts/         # Incident contact directory and threaded messaging
│   ├── notifications/    # In-app, push, and email notifications
│   ├── inbound_mail/     # IMAP polling, phishing ingestion, contact reply handling
│   └── api/              # Cross-app API utilities
├── frontend/             # React + Vite SPA
│   └── src/
│       ├── pages/        # Route-level page components
│       ├── components/   # Shared UI components
│       └── context/      # React context (org selection, auth)
└── deployment/           # Helm chart and Kubernetes manifests
```
