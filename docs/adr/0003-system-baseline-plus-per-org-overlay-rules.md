# Correlation Rules: system baseline + per-org overlay

Polaris operates the SOC for many tenant organisations. Correlation Rules are owned
two ways: **system rules** (authored centrally, `organization = null`, applied to
every tenant) provide baseline detection coverage so a new tenant gets value on
day one; **org rules** (`organization` set) let a tenant add their own detections.
Tenants cannot edit system rules but can **mute** (disable) individual system
rules for themselves via a per-org enablement table.

## Considered Options

- **System + org overlay (chosen)** — baseline coverage everywhere, per-tenant tuning without global deletion.
- **Per-org only** — every new tenant starts with an empty, useless engine; no way to ship a detection to all.
- **Global only** — one noisy rule can't be tuned out for a single tenant.

## Consequences

- `CorrelationRule.organization` is nullable; `null` = system/global.
- A per-org mute table records which system rules a tenant has disabled.
- Evaluation for an alert considers: system rules not muted by that org, plus that org's own rules.
