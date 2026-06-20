# Platform

Cross-cutting platform capabilities: [Notifications](#notifications), [Responsive UI & List Conventions](#responsive-ui--list-conventions), the [Status Page](#status-page), the [Blog / Knowledge Base](#blog--knowledge-base), and [Multi-Organisation & Access Control](#multi-organisation--access-control).

---

## Notifications

Stay informed without polling.

- In-app notification centre for incident assignments, state changes, and comments.
- Web push notifications (VAPID) so analysts get notified even when the tab is not in focus.
- Per-user notification preferences to control which events trigger alerts.
- Email notifications with customisable templates.
- **Clear all** — the notifications drawer can clear every notification at once instead of dismissing them one by one.

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
