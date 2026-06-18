# Internet-facing as a derived Host Asset status backed by an Exposure read-model

## Context

The LLM-assisted flows (the **Hunt** in-scope asset inventory and the **Incident Assistant**)
need to know which customer hosts present external attack surface, and *how* they are
exposed, to reason actionably about an attacker. A **Host Asset** can be reachable from the
internet via more than one path at once.

## Decision

**Internet-facing** is a *derived* status of a **Host Asset** — true exactly when the host has
one or more **Exposures** — never a free-standing operator-toggled boolean. An Exposure is a
unifying read-model over two differently-backed kinds:

- **Ingress-route exposures** are *derived-on-read* from an explicit `Route.backend_asset`
  FK (the org's `ingress.Route` behind the WAF). The FK is the single source of truth; nothing
  is re-stored. The app *suggests* the link by matching the route's `backend_host`, but
  **auto-applies it only on an unambiguous exact `ip_address` match** (name/hostname hits are
  surfaced as a non-committing suggestion); the link recomputes when either the route or the
  host asset changes.
- **Direct-NAT exposures** are *persisted rows* (the app has no other record of them),
  **one per forwarded service** (protocol + port, optional public IP, optional description).

Every Exposure carries a first-class **protection** trait: ingress-route exposures are
**protected** (behind the BunkerWeb WAF), direct-NAT exposures are **raw**. The flows surface
the full per-exposure list including this trait, not just a boolean.

## Considered options

- **String-matching `backend_host` → host with no explicit FK** (rejected): a *missed* match
  silently renders a genuinely-exposed host as not internet-facing — a dangerous false-negative
  in a security tool. NetBird overlay IPs and NAT'd backends defeat naive matching outright.
- **A single uniform stored `Exposure` table with Route-signal sync** (rejected): re-stores
  information already canonical in `Route.backend_asset`, adding a staleness/sync-bug surface
  for no new information. The asymmetric (derived ingress / stored NAT) split keeps one source
  of truth per kind.

## Consequences

- NetBird routes (`backend_type=netbird`) still get the explicit link and a normal ingress-route
  exposure, but their `backend_host` is an overlay IP that won't auto-match; the suggestion is
  **stubbed with a placeholder** until NetBird-aware resolution is implemented.
- A route pointing at an as-yet-untracked host stays unlinked until that **Host Asset** exists;
  link computation is bidirectional, so the host picks up its routes when created.
