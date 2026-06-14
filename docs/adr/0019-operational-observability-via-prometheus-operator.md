# Operational observability via the existing Prometheus Operator; tenant-agnostic metrics

We monitor the platform's own performance and availability by **plugging into the Prometheus Operator / kube-prometheus-stack that is already running in the cluster** (Prometheus + Grafana + Alertmanager), rather than bundling a monitoring stack into the `vels-online` chart. Our chart ships `ServiceMonitor`/`PodMonitor` CRDs, a Grafana dashboard ConfigMap, and `PrometheusRule` alerts; the operator discovers and acts on them.

Observability is treated as a **separate concern from the SOC domain**. The platform's job is processing security signals (**Alert**, **Incident**, **Finding** — see `CONTEXT.md`); observability is about *operating the platform*. We keep the two vocabularies apart: a Prometheus alert is never a domain **Alert**, an app outage is never a domain **Incident**, and these operational terms stay out of the domain glossary.

## Considered options

- **Bundle kube-prometheus-stack as a chart dependency** — rejected: duplicates infrastructure the cluster already provides; "as much off-the-shelf as possible" points to reusing the operator.
- **Per-tenant operational metrics** (label request/task metrics by org) — rejected for v1: time-series cardinality explosion (orgs × views × status) and it couples ops metrics to the tenant model and leaks tenant activity into platform dashboards. **Ops metrics are deliberately tenant-agnostic.** Per-tenant *security* insight already lives in the SOC domain.

## Decisions

- **App instrumentation:** `django-prometheus` for HTTP RED metrics on the web tier, exposed on a **dedicated metrics port that is not wired to the public Ingress** (gunicorn runs multiple workers, so this uses prometheus_client multiprocess mode with a metrics listener aggregating across workers).
- **Celery:** an off-the-shelf **`celery-exporter`** runs as its own Deployment, consuming task events from the Valkey broker (requires task-sent events enabled on the workers). No worker code instrumentation.
- **Infra:** reuse built-in exporters of off-the-shelf components — CNPG's PodMonitor and the Valkey metrics exporter — plus cluster kube-state-metrics for pod health.
- **Insights:** ship a starter Grafana dashboard and a small set of `PrometheusRule` alerts (app down, high 5xx rate, Celery backlog/failure, pod crashloop).

## Consequences

- Depends on the cluster operator's CRDs and a configured Alertmanager; the chart is not self-contained for monitoring by design.
- Readiness/liveness probes against `/api/health/` are **out of scope here** and tracked separately, even though they serve the same "availability" goal.
