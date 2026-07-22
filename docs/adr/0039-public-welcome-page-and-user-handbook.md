# A public welcome page and user handbook at the app's root

[ADR-0037](0037-extract-personal-site-mssp-app-login-first.md) collapsed `/` to a
**login-first** front door: an unauthenticated visitor was redirected straight into the
Authentik OIDC login, with no page in between. In practice that reads as broken rather
than as minimal — a bare redirect gives a first-time visitor nothing to orient against,
and existing users no place to look something up without signing in first.

We are re-introducing a public surface on the platform, at `/` (welcome) and `/docs`
(the end-user handbook). This **partially supersedes ADR-0037**, whose "keep a trimmed
product-marketing landing on the MSSP app" option was rejected. The reasoning has
changed: the deciding need here is **end-user documentation** — reference material that
must be linkable, readable without an account, and versioned alongside the UI it
describes — with the product framing being a secondary benefit. Marketing for the
personal brand still lives on the separate static site at `www.vels.online`; this page
documents *the platform*, not the brand, so it does not recreate the coupling 0037
removed.

Authenticated users never see the welcome page: `LandingPage` sends them to
`/dashboard`, exactly as the bare redirect did. `/docs` is readable by everyone.

Headline figures on the welcome page come from a new **`GET /api/public/stats/`**:
unauthenticated, cached (15 min), and per-IP throttled (60/hour). It exposes only
whole-platform aggregates — no organisation names, no per-tenant breakdown. The
Infrastructure pseudo-org ([ADR-0017](0017-shared-infrastructure-pseudo-org-for-agentless-hunting.md)) is
excluded from the tenant count, since it owns no customer.

## Considered Options

- **Public welcome + separate `/docs` page, real stats endpoint (chosen)** — the handbook
  gets a URL worth sharing and room to grow; the landing page stays a short pitch. Costs
  one new public endpoint and its cache/throttle surface.
- **Welcome page with the handbook inlined below it** — prototyped and rejected: it made
  a single enormous page, buried the pitch, and gave documentation no linkable home.
- **Documentation-only page, no welcome page** — leaves `/` as the bare redirect this ADR
  exists to fix.
- **Hardcoded or omitted statistics** — omitting them weakens the page; hardcoding them
  publishes claims about the business that drift out of true the moment they are written.
  Rejected in favour of figures the platform can actually stand behind.
- **Serving the handbook content from the backend** — would allow copy edits without a
  frontend deploy, but the prose describes UI behaviour and should version with the UI.
  Content lives in `frontend/src/content/siteContent.js`; this stays revisitable.

## Consequences

- `PublicLayout` no longer wraps only `/signup` and `/status`; the two new routes use a
  separate `LandingLayout` because they own a dark full-bleed treatment rather than the
  app's container-width shell.
- The stats endpoint is the platform's first deliberately unauthenticated read of
  aggregate customer data. Its query set is the contract — anything added to it is a
  public disclosure decision, not a display decision.
- "Incidents resolved" is counted from `state` plus `updated_at`, because `Incident` has
  no `closed_at`. It is an approximation; making it exact means adding that column.
- Documentation copy is now a frontend concern. A wording fix ships as a normal release.
