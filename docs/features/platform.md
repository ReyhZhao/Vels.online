# Platform

Cross-cutting platform capabilities: [Notifications](#notifications), the [Live Attack Map](#live-attack-map), [Responsive UI & List Conventions](#responsive-ui--list-conventions), the [Status Page](#status-page), the [Blog / Knowledge Base](#blog--knowledge-base), and [Multi-Organisation & Access Control](#multi-organisation--access-control).

---

## Notifications

Stay informed without polling.

- In-app notification centre for incident assignments, state changes, and comments.
- Web push notifications (VAPID) so analysts get notified even when the tab is not in focus.
- **iOS PWA app-icon badge** — when installed as a home-screen app on iOS, the app icon carries a badge showing the unread-notification count, so analysts see outstanding work without opening the app.
- Per-user notification preferences to control which events trigger alerts.
- Email notifications with customisable templates.
- **Clear all** — the notifications drawer can clear every notification at once instead of dismissing them one by one.

---

## Live Attack Map

A staff-only, cross-org SOC dashboard that animates recent **Attacks** — geo-locatable inbound Wazuh events — in near-real-time, drawn as arcs from the source country to the targeted organisation, with side panels for top source countries, top attack types, and the current rate.

- **Read-model projection, not a new signal** — an Attack is any inbound event at or above a configurable severity floor whose source resolves to a real foreign country (from Wazuh GeoIP enrichment, else a firewall decoder's country field). It visualises existing raw events; it does not create or store new detections, and it sits *outside* the alert→incident pipeline.
- **Cheap regardless of audience** — a single background producer computes one shared snapshot on a fixed (~10s) cadence and every viewer reads that same copy over SSE, so load on the Wazuh OpenSearch backend stays constant no matter how many staff open the map. The producer is **presence-gated**: with zero viewers it short-circuits before touching OpenSearch, bounding total backend load to a handful of queries per minute and zero when unwatched.
- **Paints immediately, then tails live** — a capped, time-bounded shared buffer backfills a newly-connected client so the map paints at once, then the client tails new arcs live; client-side arc animation carries the live feel between producer ticks.
- **Global by design** — the map is deliberately cross-org and staff-only (a tenant cannot see the shared perimeter, which carries no per-org attribution), and it visualises the security domain rather than platform health. v1 is inbound-only; an egress axis and a per-org map are deferred.

---

## Responsive UI & List Conventions

Consistent list affordances and a mobile-friendly layout across every admin and operator surface.

- **Filter / sort / search everywhere** — list pages (incidents, alerts, assets, contacts, tasks, routes, exceptions, correlation & search rules, automations, Wazuh responses, hunts, posts, and more) share the same controls: free-text search, sortable columns, and status/facet filters.
- **Mobile card stacking** — on narrow viewports, wide tables collapse into stacked cards so the platform is usable on a phone, not just a desktop SOC console.
- **Bulk actions** — multi-select with bulk operations (archive, delete, promote, etc.) where it makes sense, so operators can clear or action many rows at once.

These conventions are documented for contributors in [`docs/agents/frontend-conventions.md`](../agents/frontend-conventions.md).

---

## Status Page

A public-facing status page showing the health of the platform's own services, suitable for embedding or linking to from a customer portal.

---

## Blog / Knowledge Base

Built-in blog for publishing security advisories, runbook documentation, or customer-facing updates — managed from the admin panel.

---

## Multi-Organisation & Access Control

- Organisations are fully isolated; members only see their own data.
- Invitation flow with expiry for onboarding new team members.
- SSO via Authentik (OIDC) for production deployments; falls back to Django local auth for development.
- Role-based membership (admin vs. member) controls what each user can configure.
