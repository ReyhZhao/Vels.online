# Getting Started

How to run Vels.online locally, configure it, and deploy it to Kubernetes.

---

## Prerequisites

- Docker and Docker Compose
- A running Wazuh instance (optional for local dev)

---

## Run locally

```bash
git clone https://github.com/<your-org>/vels-online.git
cd vels-online
docker compose up --build
```

The backend will be available at `http://localhost:8000` and the frontend at `http://localhost:5173`.

Default admin credentials (local dev only): `admin` / `admin`.

---

## Environment variables

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
| `OLLAMA_API_KEY` | Ollama Cloud API key — enables native web search for the agentic assistants (omit on self-hosted Ollama to run in degraded, app-data-only mode) |
| `GOOGLE_API_KEY` | Google API key (if using Gemini provider) |
| `GEMINI_MODEL` | Gemini model id — must be a Gemini 3 model to combine web-search grounding with function tools for the agentic assistants |
| `AUTHENTIK_SERVER_URL` | Authentik OIDC server URL (leave blank to disable SSO) |
| `BUNKERWEB_API_URL` | BunkerWeb API URL (for ingress route management) |
| `SEMAPHORE_API_URL` | Semaphore API URL (for automation tasks) |
| `GITHUB_TOKEN` | GitHub PAT for pushing Wazuh exception rules |
| `ABUSEIPDB_API_KEY` | AbuseIPDB API key (for IOC enrichment) |
| `VIRUSTOTAL_API_KEY` | VirusTotal API key (for IOC enrichment) |
| `ONCALL_ROUTING` | Post-triage incident routing mode: `always` (default) routes every triaged incident; `llm_guided` routes only on escalation recommendations |
| `IMAP_HOST` | IMAP server host (for inbound contact replies and phishing ingestion) |
| `IMAP_USER` | IMAP account username |
| `IMAP_PASSWORD` | IMAP account password |
| `CORRELATION_LLM_PROVIDER` | Dotted path to LLM provider for the correlation rule-author assistant |
| `ASSISTANT_LLM_PROVIDER` | Dotted path to LLM provider for the incident assistant |
| `OPENSEARCH_URL` | Wazuh OpenSearch base URL (for Scheduled Search Rules and field-catalog queries) |
| `OPENSEARCH_USER` | OpenSearch username |
| `OPENSEARCH_PASSWORD` | OpenSearch password |

---

## Kubernetes / Helm

A Helm chart is provided under `deployment/`. See `deployment/values.yaml` for the full configuration reference.

---

## Monitoring & observability

The platform's own performance and availability are monitored by plugging into the **Prometheus Operator / kube-prometheus-stack already running in the cluster** (Prometheus + Grafana + Alertmanager) rather than bundling a monitoring stack into the chart. The chart ships `ServiceMonitor`/`PodMonitor` CRDs, a Grafana dashboard ConfigMap, and `PrometheusRule` alerts (app down, high 5xx rate, Celery backlog/failure, pod crashloop), which the operator discovers and acts on automatically.

- **App metrics** — `django-prometheus` exposes HTTP RED metrics on a dedicated metrics port that is **not** wired to the public Ingress (multiprocess mode aggregates across gunicorn workers).
- **Celery** — an off-the-shelf `celery-exporter` Deployment consumes task events from the Valkey broker (requires task-sent events enabled on the workers); no worker code instrumentation.
- **Infra** — reuses the built-in exporters of CNPG (PostgreSQL) and Valkey, plus cluster kube-state-metrics for pod health.

Operational metrics are deliberately **tenant-agnostic** — monitoring *the platform* is kept separate from the per-organisation SOC domain (a Prometheus alert is never a domain Alert; an app outage is never a domain Incident). This requires the cluster's Prometheus Operator CRDs and a configured Alertmanager; the chart is intentionally not self-contained for monitoring.
