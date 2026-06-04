# Normalised entity correlation via an ECS entity envelope, supplied at the boundary

To correlate heterogeneous alerts across different sources and agents (e.g. a
user-creation → login → scheduled-task chain joined on username), alerts need
shared, normalised entities. We decided **not** to build platform-side per-source
extractors. Instead, every alert must carry a normalised **entity envelope** whose
field names follow the **Elastic Common Schema (ECS)** (`host.name`, `source.ip`,
`user.name`, `file.hash.sha256`, `process.name`, …). Sources populate it (the Wazuh
shipper maps Wazuh's already-ECS-ish data; the ingestion API makes the envelope a
required field so external tools must supply it), and the platform canonicalises
values on ingest (case-fold, strip domain) so cross-source joins line up.

## Considered Options

- **ECS (chosen)** — Wazuh already maps to ECS; external SIEM/EDR tools commonly speak it; minimal transformation.
- **OCSF** — newer, broader, heavier than an entity envelope needs.
- **Custom vocabulary** — simplest to control but reinvents a subset of ECS and forces every integrator to learn bespoke names.
- **Platform-side extractors** — rejected; fragile per-source parsers that rot as payloads change.

## Consequences

- The ingestion API contract becomes versioned/breaking for existing integrations — they must start sending the envelope.
- A canonicalisation step is still required on ingest; "required field" guarantees presence, not format consistency.
- A new correlatable entity = an ECS field + shipper mapping, not platform parser work.
