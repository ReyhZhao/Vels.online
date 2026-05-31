# Vels.online

**Vels.online** is an open-source Managed Security Service Provider (MSSP) platform. It gives security teams a unified workspace to monitor infrastructure, respond to incidents, manage vulnerabilities, publish services safely to the internet, and automate repetitive operational work — all from a single multi-tenant application.

The platform is built around a Wazuh-integrated SOC workflow: detections flow in from Wazuh agents (and other sources) as **Alerts**, get triaged (manually or by an LLM), and are worked to resolution through structured playbooks. Everything is scoped per organisation so an MSSP can manage multiple customers from one deployment.

---

## Screenshots

> _Screenshots coming soon._

| Dashboard | Incident Detail | Security Overview |
|-----------|----------------|------------------|
| ![Dashboard placeholder](docs/screenshots/dashboard.png) | ![Incident placeholder](docs/screenshots/incident-detail.png) | ![Security placeholder](docs/screenshots/security-dashboard.png) |

| Ingress Routes | Vulnerability Dashboard | Fleet / Agents |
|---------------|------------------------|----------------|
| ![Routes placeholder](docs/screenshots/routes.png) | ![Vulns placeholder](docs/screenshots/vulnerabilities.png) | ![Fleet placeholder](docs/screenshots/fleet.png) |

---

## Features

### Alert Ingestion Pipeline

A pre-incident layer that records every detection before it becomes an incident.

- **Alert inbox** — every external detection lands as an `AL-NNN` Alert record, visible at `/alerts/`, regardless of whether a matching incident already exists. No detection is silently discarded.
- **Smart auto-routing** — high and critical severity alerts with no matching open incident auto-promote to new incidents immediately; low and medium alerts sit in the inbox for analyst review.
- **Duplicate suppression** — incoming alerts are matched against open incidents by Wazuh rule ID or rule description within a configurable lookback window; matches auto-link to the existing incident instead of creating a duplicate.
- **Asset threshold promotion** — sustained low-severity alerts against the same asset within a configurable time window auto-promote to a new incident even when individual severities are low.
- **Bulk promote** — select multiple alerts from the inbox and promote them to a single incident in one action.
- **Linked Alerts panel** — every incident shows a collapsible panel listing all `AL-NNN` records behind it, with state badges and timestamps.
- **Alert enrichment passthrough** — third-party tools (N8N, webhooks) can pass `title`, `description`, `severity`, `pap`, and `tlp` at ingestion time; promoted incidents inherit these values instead of auto-derived placeholders.
- **Per-org thresholds** — configure the auto-promote count, time window, and match lookback window per organisation in settings.

### Incident Management

A full lifecycle for security incidents, from detection to closure.

- **Multi-source ingestion** — incidents are created from Wazuh alerts, phishing emails, vulnerability scans, agent findings, or manually by analysts.
- **Severity tiers** — Critical · High · Medium · Low · Info, with SLA tracking displayed in the incident list. Severity auto-escalates when a new linked alert has a higher severity than the current incident.
- **Structured playbooks** — subject-based task templates automatically apply the right checklist (phishing, malware, vulnerability, etc.) when an incident is created.
- **Immutable audit trail** — every state change, comment, delegation, attachment, and alert link is timestamped in a timeline for complete accountability.
- **Extended close flow** — close incidents as resolved or as a duplicate linked to a canonical incident; a searchable combobox makes finding the canonical incident fast even across large lists.
- **Auto-closure** — incidents older than 7 days in `new`, `triaged`, or `resolved` state are automatically closed, keeping the active queue clean.
- **Delegation and transfers** — analysts can temporarily hand off work to teammates and receive it back, maintaining a clear chain of responsibility.
- **TLP/PAP-aware communications** — sensitive findings are gated by classification level so customers see exactly what they are entitled to see.
- **Persistent filter & sort preferences** — each user's chosen filters and sort order are remembered across sessions.
- **Tab counters** — incident detail tabs (Tasks, Contacts, IOCs, Assets, Attachments, Linked Alerts) show item counts at a glance.
- **Smart page refresh** — the incident detail page detects when new data is available (triage result, new alert link, comment) and prompts for a reload without forcing a full refresh.
- **Multi-organisation support** — each organisation has its own incident queue, team, and settings; admins can manage all orgs from one account.

### Inbound Phishing Ingestion

Turn phishing reports into incidents with zero analyst effort.

- Forward any suspected phishing email to `soc@vels.online`; the platform creates an incident automatically.
- Parses forwarded and attached `.eml` files; extracts raw email body as the incident description.
- Extracts URLs, domains, and sender addresses as IOCs and enriches them immediately (see IOC Enrichment below).
- LLM triage annotates phishing incidents with email-specific context (sender reputation, URL risk, attachment analysis).

### IOC Enrichment

Automatically assess every indicator of compromise at incident creation time.

- **IP addresses** — queried against AbuseIPDB; results include abuse confidence score, total reports, country, and usage type.
- **Domains and URLs** — queried against VirusTotal; malicious/suspicious vote counts surfaced inline.
- Enrichment data is available to the AI triage pipeline immediately, improving the quality of automated assessments.
- Enriched IOCs display threat intelligence details in the IOC tab without requiring analysts to leave the platform.

### AI-Powered Triage

Reduce analyst workload on repetitive alert screening.

- LLM analyses each incident (title, description, raw Wazuh event, linked assets, IOCs and their enrichment data) and returns a structured assessment: recommended severity, 2–3 sentence summary, primary and secondary suggested actions, and a false-positive confidence score.
- **Pluggable providers** — ships with Google Gemini and Ollama backends; swap via a single environment variable (`TRIAGE_LLM_PROVIDER`).
- **Per-org custom context** — admins can add organisation-specific prompt context (e.g. known safe IPs, environment notes) to sharpen triage accuracy for their estate.
- **Customisable LLM prompt** — org admins can edit the base triage prompt directly from the settings page to tune the model's behaviour for their environment.
- Triage results surface in the incident timeline as a labelled AI comment with recommended actions shown inline; analysts accept or override with one click.
- Triage status is prominently displayed on the incident detail page; a smart-reload banner appears the moment a triage result arrives.

### Fleet & Asset Management

Visibility into the devices and agents across your monitored estate.

- Wazuh agent sync runs on a daily schedule, automatically populating the Asset registry from the Wazuh API — no manual entry needed.
- **Permanent assets** — manually created or API-imported assets can be flagged as permanent so they are not removed by the automated expiry cleanup.
- Per-agent detail pages show status, OS, IP address, last keepalive, and linked incidents.
- Fleet events feed shows real-time activity across all agents.
- Assets can be manually added and assigned to Contacts (see below).

### Vulnerability Management

Track and remediate CVEs across the estate.

- **Vulnerability snapshots** — periodic counts of Critical/High/Medium/Low findings per organisation, trended over time on the vulnerability dashboard.
- **CVE advisories** — fetches remediation guidance from Ubuntu Security and Microsoft MSRC for CVEs found in the estate (Ubuntu and Windows platforms supported).
- **Work packages** — group related vulnerabilities into a tracked remediation effort with per-item status (Open · In Progress · Resolved · Accepted Risk).
- **Risk acceptance** — formally accept a CVE with a justification; accepted risks are surfaced separately and do not pollute the active queue.

### Exception Rules

Suppress known-good alerts so analysts focus on real threats.

- Create Wazuh exception rules from within the platform with a form-based UI (no XML editing required).
- Rules are assembled into valid Wazuh XML and pushed directly to a GitHub repository via the API; the Wazuh deployment picks them up on its next sync.
- IDs are allocated from a managed pool to avoid collisions; freed IDs are recycled automatically.
- Approval workflow: exceptions require review before the GitHub push is made.

### App Ingress (Reverse Proxy & WAF)

Let customers safely publish their own services to the internet without manual infrastructure work.

- **Self-service route management** — create ingress routes mapping a public FQDN to any backend host:port, scoped to the organisation.
- **Automatic SSL termination** — BunkerWeb provisions and renews Let's Encrypt certificates automatically; the creation form shows the DNS A-record target and a background check warns if DNS is not yet aligned.
- **Web Application Firewall** — ModSecurity with the OWASP Core Rule Set protects every route. Configurable paranoia level (1–4) per route.
- **Rate limiting** — per-route request rate and burst limits to guard against traffic spikes and credential-stuffing.
- **Country access controls** — blacklist or whitelist countries per route for geography-based access policies.
- **Blocked activity reports** — live feed of blocked requests (source IP, rule triggered, action taken) fetched on demand from BunkerWeb.
- Routes support both direct (public IP) and NetBird (overlay network) backend types.

### Automations

Trigger runbook-style workflows without leaving the platform.

- Automations map to Semaphore CI/CD templates; analysts can launch them from incident tasks with optional variable overrides.
- **Incident var mappings** — each automation can declare a YAML mapping from Semaphore playbook variable names to incident data sources (linked assets, IOCs, core incident fields). Variables are resolved automatically at run time — no manual copy-paste.
- **Pre-run preview modal** — before launching an automation, analysts see a preview of all resolved variables so they can verify the correct data will be passed.
- Task templates can be pre-wired to an automation so the right runbook fires automatically when a checklist item is started.
- In-progress automation status is tracked and surfaced on incident tasks in real time.
- Automation output and feedback are collected and displayed on the task after the run completes.

### Incident Contacts

Link employees and asset owners to incidents for structured communication.

- **Contact directory** — per-organisation directory of natural persons (employees, contractors, asset owners) with name, email, job title, and department.
- **Asset ownership** — assign assets to contacts; when an incident is created and an asset is linked, the owner contact is automatically associated with the incident.
- **In-platform Q&A** — analysts can message a contact directly from an incident (role: `notified` or `questioned`); the platform sends the email and ingests replies back into the incident timeline via IMAP polling.
- **Threaded messaging** — outbound questions and inbound replies are displayed as a conversation thread within the incident detail.

### Notifications

Stay informed without polling.

- In-app notification centre for incident assignments, state changes, and comments.
- Web push notifications (VAPID) so analysts get notified even when the tab is not in focus.
- Per-user notification preferences to control which events trigger alerts.
- Email notifications with customisable templates.

### Status Page

A public-facing status page showing the health of the platform's own services, suitable for embedding or linking to from a customer portal.

### Blog / Knowledge Base

Built-in blog for publishing security advisories, runbook documentation, or customer-facing updates — managed from the admin panel.

### Multi-Organisation & Access Control

- Organisations are fully isolated; members only see their own data.
- Invitation flow with expiry for onboarding new team members.
- SSO via Authentik (OIDC) for production deployments; falls back to Django local auth for development.
- Role-based membership (admin vs. member) controls what each user can configure.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5 · Django REST Framework · Celery · django-celery-beat |
| Database | PostgreSQL 16 |
| Cache / broker | Valkey (Redis-compatible) |
| Frontend | React 18 · Vite · Tailwind CSS · shadcn/ui |
| LLM providers | Google Gemini · Ollama (pluggable) |
| Security monitoring | Wazuh |
| Threat intelligence | AbuseIPDB · VirusTotal |
| WAF / reverse proxy | BunkerWeb (ModSecurity + OWASP CRS) |
| Automation runner | Semaphore CI |
| Identity provider | Authentik (OIDC) |
| Container runtime | Docker / Kubernetes (Helm chart included) |

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- A running Wazuh instance (optional for local dev)

### Run locally

```bash
git clone https://github.com/<your-org>/vels-online.git
cd vels-online
docker compose up --build
```

The backend will be available at `http://localhost:8000` and the frontend at `http://localhost:5173`.

Default admin credentials (local dev only): `admin` / `admin`.

### Environment variables

Copy `backend/.env.example` to `backend/.env` and fill in the values:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Valkey/Redis connection string |
| `WAZUH_API_URL` | Wazuh manager API base URL |
| `WAZUH_API_USER` | Wazuh API username |
| `WAZUH_API_PASSWORD` | Wazuh API password |
| `TRIAGE_LLM_PROVIDER` | Dotted path to triage provider class (e.g. `incidents.llm.ollama.OllamaTriageProvider`) |
| `OLLAMA_BASE_URL` | Ollama server URL (if using Ollama provider) |
| `OLLAMA_MODEL` | Model name (e.g. `gemma4:31b-cloud`) |
| `GOOGLE_API_KEY` | Google API key (if using Gemini provider) |
| `AUTHENTIK_SERVER_URL` | Authentik OIDC server URL (leave blank to disable SSO) |
| `BUNKERWEB_API_URL` | BunkerWeb API URL (for ingress route management) |
| `SEMAPHORE_API_URL` | Semaphore API URL (for automation tasks) |
| `GITHUB_TOKEN` | GitHub PAT for pushing Wazuh exception rules |
| `ABUSEIPDB_API_KEY` | AbuseIPDB API key (for IOC enrichment) |
| `VIRUSTOTAL_API_KEY` | VirusTotal API key (for IOC enrichment) |
| `IMAP_HOST` | IMAP server host (for inbound contact replies and phishing ingestion) |
| `IMAP_USER` | IMAP account username |
| `IMAP_PASSWORD` | IMAP account password |

### Kubernetes / Helm

A Helm chart is provided under `deployment/`. See `deployment/values.yaml` for the full configuration reference.

---

## Project Structure

```
.
├── backend/              # Django application
│   ├── alerts/           # Alert ingestion pipeline, inbox, auto-routing
│   ├── incidents/        # Incident lifecycle, tasks, LLM triage
│   ├── security/         # Organisations, assets, vulnerabilities, CVE advisories
│   ├── exceptions/       # Wazuh exception rule management
│   ├── ingress/          # BunkerWeb-backed reverse proxy routes
│   ├── automations/      # Semaphore automation wrappers
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

---

## Contributing

Pull requests are welcome. Please open an issue first to discuss significant changes.

---

## License

[MIT](LICENSE)
