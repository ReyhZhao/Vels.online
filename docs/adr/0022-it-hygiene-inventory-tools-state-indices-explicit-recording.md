# IT Hygiene Inventory tools: read state indices, record evidence via an explicit two-step

## Status

accepted

## Context

The **Incident Assistant** ([ADR-0011](0011-assistant-agentic-tool-calling-loop.md)/[ADR-0012](0012-incident-assistant-relaxed-action-authority.md)) and the **Hunt** module ([ADR-0015](0015-threat-hunting-incident-producing-module.md)) both reason over Wazuh telemetry, but neither can see a host's **IT Hygiene Inventory** — its installed software, running processes, and services. Operators want the LLM to answer "what is installed/running on this host?" (incident-bound) and "which hosts anywhere run X?" (fleet-wide hunting), and to be able to *log* a compromised piece of software as evidence even when no alert ever fired for it.

Wazuh 4.14 exposes this two ways: the per-agent **syscollector REST API** (already used by the hunt `agent_processes`/`agent_ports` lenses) and the **IT Hygiene Inventory state indices** in OpenSearch (`wazuh-states-inventory-{packages,processes,services,…}-wazuh`). The API has no "services" collection and cannot search across the fleet; the indices model all three kinds and are aggregatable. A `Finding` has until now meant a matched *alert* document.

## Decision

**Read inventory from the OpenSearch state indices, not the syscollector API.** New tools query `wazuh-states-inventory-{kind}-*` through the existing `OpenSearchClient`, under the same per-org `agent.id` scoping as every other Wazuh query — so "services" becomes reachable and fleet value-search is possible.

Give each surface the tool shape that fits it (not a symmetric pair):

- **Hunt** — `inventory_search(kind, query)` fans out per org and returns *matching hosts + counts*, **summary-only**. `kind` is an allowlisted enum `{software, service, process}` (one parameterised tool, mirroring `top_values(field=…)` and keeping the schema tight for the Ollama runtime).
- **Incident Assistant** — `host_inventory(agent_name, kind, query?)` lists one host's inventory, **org-scoped to the incident's organisation** (host resolved via `get_agents(wazuh_group)`; collisions across orgs blocked). No staff `scope="all"` widen — a full-fleet inventory dump is a Hunt's job.

**Inventory matches become Findings only through a deliberate, explicit step.** A Hunt records inventory evidence with a separate `record_inventory_finding(agent_name, kind, name, summary)` tool, *not* by the lens auto-recording every match. The model-supplied `summary` becomes the materialised Alert's title. Recorded inventory docs ride the existing propose-and-confirm + materialise bridge unchanged (the bridge is already shape-tolerant: host from `agent.name`, no `rule.description` required).

## Considered Options

- **Syscollector REST API instead of the indices.** Rejected: it has no services collection, is per-agent only (cannot answer "which hosts run X?"), and would force a third client path. The indices give all three kinds and fleet aggregation behind the one client the lenses already use.
- **One symmetric inventory tool shared by both surfaces.** Rejected: a per-agent dump makes the Hunt weak (it could only inspect hosts it already suspects, never sweep) and a typical host's hundreds of packages would blow the context window.
- **IOC-style auto-record (match *is* evidence).** Rejected for inventory: unlike an IOC sweep, where the input (a known-bad hash) encodes the judgment, a bare software/service/process *name* match is mostly benign (`openssl` is everywhere). Auto-recording would flood the propose-and-confirm queue with benign hosts. The compromise judgment is the model's, made *after* the search — so recording is a deliberate act, mirroring how a human hunter sweeps, judges, then logs the bad one.
- **Summary-only inventory (no Findings at all).** Rejected: IOCs are often sparsely populated and compromised software may raise *no* alert, so the inventory row can be the only evidence. "Pivot to `ioc_search` for the real Finding" fails exactly when it matters.

## Consequences

- **A `Finding` now spans two document kinds** — alert docs and inventory-state docs. The glossary's `Finding` definition is updated accordingly. Materialised inventory Alerts carry no `rule.description` and lean on the model-supplied `summary` for a readable title.
- **Process data is reachable two ways in a Hunt** (live per-agent syscollector pull vs. fleet inventory value-search). Kept deliberately — see the Flagged ambiguity in `CONTEXT.md`. Software and services exist *only* in the inventory indices.
- **New index dependency.** The tools assume `wazuh-states-inventory-*-wazuh` exist and are populated; field projections are a tight per-kind allowlist verified against each index's mapping at build time.
- **No new action authority.** Assistant inventory reads are read tools under the existing agentic pattern; the Hunt's `record_inventory_finding` commits Findings, which still reach an Incident only through human propose-and-confirm. No PAP guard is needed — inventory reads touch the org's own internal data, not external disclosure.
- **Phase-agnostic.** Because the search lens commits nothing, it behaves identically in a Hunt's **Scoping** and **Searching** phases; only `record_inventory_finding` is gated by the non-persisting Scoping sink.
