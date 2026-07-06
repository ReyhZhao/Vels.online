# Partner intake: direct Incidents over DKIM/SPF-verified email Connections

## Status

accepted

## Context

External **partners** — peer CSIRTs reporting detections about a customer's estate, and
software suppliers broadcasting security bulletins (Fortinet, Palo Alto, …) — need a
low-friction way to feed cases into the platform. The API already allows this
(`source_kind = external`), but partners overwhelmingly prefer **email**. A configured,
per-partner email channel (a **Connection**) is the requested v1 transport.

## Decision

A partner email creates or updates an **Incident directly** (`source_kind = "partner"`) —
it is **never** turned into an **Alert** and **never** passes through the correlation
engine. A peer SOC's detection is a fully-formed incident, not a raw signal to correlate,
and matching is by the partner's **External Reference** in the subject
(`(connection, external_reference)`), which is incident-level dedup, not entity-level
correlation.

Sender identity is the credential, made safe by **mandatory DKIM/SPF verification**
(env toggle `PARTNER_INTAKE_VERIFY_AUTH`, default **on**): a Connection sender that fails
verification is dead-lettered to the **Intake Inbox**, never ingested. Routing checks a
new `PartnerIngestionHandler` (sender ∈ a Connection's sender set) **before** the phishing
handler.

**Vendor** bulletins land as `source_kind = "partner"`, subject "Vendor Advisory",
Incidents in the **Infrastructure organisation** (the fleet-level, non-tenant home) — a
human assesses "are we affected?" and closes `no_impact`/`informational` or escalates.
Automatic affectedness-checking and fan-out to affected customer orgs are **deferred**
(they need a product/asset inventory). A **CSIRT** Connection feeds one **customer org**.

Partner Incidents ride normal **Triage** for its recommendations, but are **exempt from
Classify's unattended false-positive auto-close** — a peer's report is never silently
closed (which also protects the outbound channel from auto-announcing a wrong closure).

## Considered options

- **Alert-path (like the phishing `inbound_email` handler).** Rejected: a partner
  detection would then be subject to correlation/Supersede, and the entity-based
  correlation engine has no place for an opaque External-Reference match key. A forwarded
  phishing mail genuinely *is* a raw signal; a peer CSIRT feed is not.
- **Trust-by-shared-secret/token in the subject or a `+token` address.** Rejected for the
  primary path: partners want to email you naturally with *their* reference ID, not carry
  our token. DKIM/SPF gives cryptographic sender assurance without imposing a token on the
  partner. (The token approach still powers the human **ContactReply** flow.)
- **A dedicated internal/SOC org for vendor advisories.** Deferred: reuse the existing
  Infrastructure organisation rather than stand up a new non-tenant org, widening its role
  from shared-perimeter events to any fleet-level SOC record. Split later if the two uses
  diverge.

## Consequences

- One sender maps to exactly one Connection/org (senders unique across Connections). A
  national CSIRT reporting for many orgs from one address is **not** supported in v1 —
  per-message org resolution is deferred with affectedness/fan-out. See
  `CONTEXT.md` → *Flagged ambiguities*.
- DKIM/SPF depends on the receiving mail path stamping `Authentication-Results` that the
  IMAP-fetched message carries.
