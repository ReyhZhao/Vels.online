# Platform

Cross-cutting platform capabilities: [Notifications](#notifications), the [Status Page](#status-page), the [Blog / Knowledge Base](#blog--knowledge-base), and [Multi-Organisation & Access Control](#multi-organisation--access-control).

---

## Notifications

Stay informed without polling.

- In-app notification centre for incident assignments, state changes, and comments.
- Web push notifications (VAPID) so analysts get notified even when the tab is not in focus.
- Per-user notification preferences to control which events trigger alerts.
- Email notifications with customisable templates.

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
