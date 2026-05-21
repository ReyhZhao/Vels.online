# Vels.online

**Vels.online** is an open-source Managed Security Service Provider (MSSP) platform. It gives security teams a unified workspace to monitor infrastructure, respond to incidents, manage vulnerabilities, publish services safely to the internet, and automate repetitive operational work — all from a single multi-tenant application.

The platform is built around a Wazuh-integrated SOC workflow: alerts flow in from Wazuh agents, get triaged (manually or by an LLM), and are worked to resolution through structured playbooks. Everything is scoped per organisation so an MSSP can manage multiple customers from one deployment.

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

### Incident Management

A full lifecycle for security incidents, from detection to closure.

- **Multi-source ingestion** — incidents are created from Wazuh events, vulnerability scans, agent findings, or manually by analysts.
- **Severity tiers** — Critical · High · Medium · Low · Info, with SLA tracking displayed in the incident list.
- **Structured playbooks** — subject-based task templates automatically apply the right checklist (phishing, malware, vulnerability, etc.) when an incident is created.
- **Immutable audit trail** — every state change, comment, delegation, and attachment is timestamped in a timeline for complete accountability.
- **Delegation and transfers** — analysts can temporarily hand off work to teammates and receive it back, maintaining a clear chain of responsibility.
- **TLP/PAP-aware communications** — sensitive findings are gated by classification level so customers see exactly what they are entitled to see.
- **Multi-organisation support** — each organisation has its own incident queue, team, and settings; admins can manage all orgs from one account.

### AI-Powered Triage

Reduce analyst workload on repetitive alert screening.

- LLM analyses each incident (title, description, raw Wazuh event, linked assets, and IOCs) and returns a structured assessment: recommended severity, 2–3 sentence summary, primary and secondary suggested actions, and a false-positive confidence score.
- **Pluggable providers** — ships with Google Gemini and Ollama backends; swap via a single environment variable (`TRIAGE_LLM_PROVIDER`).
- **Per-org custom context** — admins can add organisation-specific prompt context (e.g. known safe IPs, environment notes) to sharpen triage accuracy for their estate.
- Triage results surface in the incident timeline as a labelled AI comment with the recommended actions shown inline; analysts accept or override with one click.

### Fleet & Asset Management

Visibility into the devices and agents across your monitored estate.

- Wazuh agent sync runs on a daily schedule, automatically populating the Asset registry from the Wazuh API — no manual entry needed.
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
- Task templates can be pre-wired to an automation so the right runbook fires automatically when a checklist item is started.
- In-progress automation status is tracked and surfaced on incident tasks in real time.

### Incident Contacts

Link employees and asset owners to incidents for structured communication.

- **Contact directory** — per-organisation directory of natural persons (employees, contractors, asset owners) with name, email, job title, and department.
- **Asset ownership** — assign assets to contacts; when an incident is created and an asset is linked, the owner contact is automatically associated with the incident.
- **In-platform Q&A** — analysts can message a contact directly from an incident (role: `notified` or `questioned`); the platform sends the email and ingests replies back into the incident timeline via IMAP polling.

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

### Kubernetes / Helm

A Helm chart is provided under `deployment/`. See `deployment/values.yaml` for the full configuration reference.

---

## Project Structure

```
.
├── backend/              # Django application
│   ├── incidents/        # Incident lifecycle, tasks, LLM triage
│   ├── security/         # Organisations, assets, vulnerabilities, CVE advisories
│   ├── exceptions/       # Wazuh exception rule management
│   ├── ingress/          # BunkerWeb-backed reverse proxy routes
│   ├── automations/      # Semaphore automation wrappers
│   ├── notifications/    # In-app, push, and email notifications
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
