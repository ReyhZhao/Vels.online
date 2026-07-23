# Ingest Endpoint auth: the secret UUID in the URL path is the sole credential

## Status

accepted

## Context

An **Ingest Endpoint** (`CONTEXT.md` → *Webhook ingest*; ADR-0040) exposes a public HTTP
path a remote system POSTs JSON to. It needs sender authentication. The platform already
has two relevant primitives: `ServiceAccount` (PRD #694 — a non-human API principal with a
DRF bearer token, org-scoped via `OrganizationMembership`), and the email **Connection**
pattern (ADR-0032), where *sender identity itself* is the credential (there, made safe by
DKIM/SPF). The original feature sketch called for minting "a service token with the correct
permissions" *and* a UUID path — two overlapping mechanisms.

## Decision

The **secret high-entropy UUID in the endpoint's URL path is the only credential** — a
capability URL, over TLS, exactly like Slack/CI incoming webhooks. There is **no bearer
token, no per-endpoint `ServiceAccount`, and no HMAC** in v1. The endpoint carries a plain
`organization` FK and creates records directly in that org (like the email Connection),
with `webhook` provenance for audit.

Rotating the URL is the **revoke** action (regenerate ⇒ new path, old path 404s). The
public path is guarded operationally rather than by a second credential: a body-size cap
(**413**), a per-endpoint rate limit (**429**), and paused/inactive endpoints returning
**404** (indistinguishable from a wrong URL, so a prober can't confirm a disabled endpoint
exists). Management of endpoints and inspection of Captured Payloads is **staff-only**.

## Considered options

- **Mint a `ServiceAccount` + bearer token per endpoint.** Rejected. With the adapter
  framing (ADR-0040) the create happens **in-process** — there is no logged-in user and no
  HTTP round-trip to authenticate, so an endpoint-owned token would never actually be
  *presented* by the sender. It would add a second auth principal and a token-rotation
  surface for zero benefit. `ServiceAccount` stays reserved for its real job: external
  callers of the *real* REST API.
- **UUID path *plus* a required HMAC/shared-secret signature.** Deferred, not adopted for
  v1. Many webhook senders can't sign, and the capability URL over TLS is the accepted norm
  for this class of receiver. HMAC remains a clean *optional* addition later (it does not
  change the model — it only hardens an already-authenticated path).

## Consequences

- The URL is a secret: it must never be logged in cleartext, and leaking it is equivalent
  to leaking a credential — hence the rate limit and rotate-to-revoke affordance are
  load-bearing, not nice-to-haves.
- Changing the auth model later (e.g. to require HMAC) is a **breaking change** for every
  onboarded sender, which is why this is recorded rather than left implicit.
- There is no per-sender identity within an endpoint — the endpoint *is* the identity. A
  sender that needs distinct provenance gets its own endpoint.
