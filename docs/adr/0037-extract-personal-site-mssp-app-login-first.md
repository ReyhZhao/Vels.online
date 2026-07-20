# Extract the personal marketing/blog site; MSSP app becomes login-first

The repo grew as one integrated whole: a public **personal/brand landing page** and a
**blog** sharing the same Django backend, React SPA, and Helm release as the multi-tenant
**MSSP platform**. We are splitting the two. The personal site (landing page + blog) moves
to a **separate repository** as a **static site** (Astro, file-based markdown, no backend
and no database), deployed at **`www.vels.online`**. The current repo keeps *only* the
MSSP platform; its public root `/` collapses to a **login-first** front door (unauthenticated
visitors are sent into the existing Authentik OIDC login), retaining `/signup` and `/status`
as its only other public routes.

"Dashboard" was ambiguous in the original framing: the authenticated `/dashboard`
(`DashboardPage`) is the MSSP operations home (incident/alert/vuln/agent/route KPIs and staff
queues) and **stays** with the platform — it is not part of what moves out. What moves is the
public marketing surface: the landing page (including its App Ingress / Managed Security
product-marketing sections) and the blog.

The blog is currently **empty** (no `Post` rows in production), so there is no content
migration: the `blog` Django app, its `Post` model/migrations, the `/api/posts` endpoints,
and the staff-gated authoring UI (`AdminPostList`/`AdminPostForm`, `/admin/posts*`) are
deleted outright rather than exported. The new site starts with the branding page plus an
empty Astro blog scaffold for future markdown posts. Product marketing is re-homed on the
personal site (the platform is a service offered under the personal brand), with its
"Managed Security" call-to-action deep-linking to the MSSP app's `/signup`.

## Considered Options

- **Separate static repo for the personal site (chosen)** — decouples release cadence and
  blast radius; a blog edit no longer rides the MSSP CI/Helm release train. Costs a small
  amount of duplicated presentational UI (`PostCard`, `MarkdownRenderer`, `PostSidebar`).
- **New package inside this monorepo** — keeps shared UI in one place, but preserves exactly
  the coupling the split exists to remove, and keeps the personal site chained to the
  platform's heavy backend and deploy pipeline.
- **Keep a trimmed product-marketing landing on the MSSP app** — splits the product story
  across two surfaces/domains and doubles the marketing maintenance; rejected in favour of
  a single login-first app plus all marketing on the personal site.
- **Keep the blog dynamic (small backend + web admin)** — justified only if browser-based
  authoring is required; for a single developer's blog, git-committed markdown is simpler and
  the site can go dynamic later without re-deciding the split.

## Consequences

- The MSSP app stays at the apex `vels.online` (Q5): **zero** auth/OIDC/cookie/mobile churn.
  The desired end-state (personal site fronting the apex) is deferred to a later BunkerWeb
  reverse-proxy routing change, not done now.
- The `/:slug` public catch-all route (blog post detail) is removed along with `/blog` and
  `/` — `PublicLayout` is left wrapping only `/signup` and `/status`.
- Going static is reversible: file-based markdown can be swapped for a backend + CMS later
  without revisiting the repo split.
