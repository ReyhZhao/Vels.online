# Bi-directional partner sync: mirror all external comments, gated only by is_internal and TLP:RED

## Status

accepted

## Context

A **bidirectional Connection** lets the SOC and a peer CSIRT hold a two-way conversation
*on the Incident itself*. Inbound partner messages land as external **Comment**s in the
incident timeline (see [ADR-0032](0032-partner-intake-direct-incidents-over-verified-email.md)).
The open question was the **outbound** direction: which of our changes reach the partner,
and how the analyst controls what crosses to an outside SOC — a *third* audience distinct
from both staff and the read-only customer org member.

## Decision

Outbound sync is **automatic, not an explicit "message partner" action**. Every
**staff-authored, non-internal (`is_internal = False`) Comment** is mirrored to the
partner by email, and **closure** auto-notifies them. `is_internal` is therefore the
*single* content gate: internal comments stay staff-only; external comments are the shared
working thread — sent to the partner (who can reply) and visible to the customer as
read-only progress. The partner is a co-worker on the case; the customer is a spectator.

Two guards ride on top:

- **Loop prevention (required):** only *staff-authored* external comments trigger
  outbound. Comments whose origin is the partner feed — or an AI actor (Triage Agent /
  Incident Assistant) — never echo. Each Comment records its origin.
- **TLP:RED kill switch:** at **TLP:RED** all auto-outbound (external comments + closure
  notice) is suppressed. Raising an Incident to RED is the deliberate, discoverable way to
  stop talking to the partner without changing anything else. Inbound still works.

Outbound `Subject` carries the **External Reference** so the partner's system re-threads;
our `From` is `soc@`, which matches no Connection sender, so our own mail is never
re-ingested.

## Considered options

- **Explicit "Message partner" composer** (mirroring `send_contact_message`), so nothing
  crosses to the peer without a deliberate act. Rejected by product choice: the SOC wants
  the interaction "as natural as can be" — you and the peer are both working the case, so
  ordinary external comments *should* flow. The explicit-send friction defeated that.
- **A third stored visibility level** ("partner-visible") separate from `is_internal`.
  Rejected as overkill for v1: it triples the analyst's per-comment decision. `is_internal`
  + the TLP:RED kill switch cover the real cases.
- **No TLP gate at all.** Rejected: the SOC needs *a* way to withhold a sensitive incident
  from a peer; TLP:RED is a field analysts already set, so it doubles as the off switch.

## Consequences

- The customer, viewing the incident, sees the SOC↔partner external thread unfold — this
  is intended ("they can view the case progressing from their end").
- `is_internal` now carries a second meaning ("does not go to the partner") on top of its
  existing "hidden from the customer org member." Acceptable because both reduce to "keep
  this off the shared thread," but worth remembering when reasoning about the flag.
