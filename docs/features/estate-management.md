# Estate Management

Visibility into and control over the monitored estate: [Fleet & Asset Management](#fleet--asset-management), [Vulnerability Management](#vulnerability-management), and [App Ingress](#app-ingress-reverse-proxy--waf).

---

## Fleet & Asset Management

Visibility into the devices and agents across your monitored estate.

- Wazuh agent sync runs on a daily schedule, automatically populating the Asset registry from the Wazuh API — no manual entry needed.
- **Permanent assets** — manually created or API-imported assets can be flagged as permanent so they are not removed by the automated expiry cleanup.
- Per-agent detail pages show status, OS, IP address, last keepalive, and linked incidents.
- Fleet events feed shows real-time activity across all agents.
- Assets can be manually added and assigned to Contacts (see [Incident Contacts](incident-response.md#incident-contacts)).
- **Internet-facing status (derived, never toggled)** — a Host Asset is shown as internet-facing exactly when it has one or more **Exposures**; it is never a free-standing operator-flipped boolean, so a host can't be silently mislabelled as safe. Each exposure carries a **protection trait** so analysts (and the LLM flows) see not just *that* a host is reachable but *how*:
  - **Ingress-route exposures** are derived-on-read from the [Route](#app-ingress-reverse-proxy--waf) that points at the host (the `Route → backend_asset` link is the single source of truth) and are **protected** — they sit behind the BunkerWeb WAF. The app suggests the link by matching the route's backend host and **auto-applies it only on an unambiguous exact IP match**; name-only hits are surfaced as a non-committing suggestion.
  - **Direct-NAT exposures** are explicitly recorded rows — one per forwarded service (protocol + port, optional public IP and description) — and are **raw** (no WAF in front). A NAT exposure editor on the host lets operators record these directly.
- **Surfaced to the LLM flows** — the per-exposure list (with protection trait) feeds the [Incident Assistant](incident-response.md#incident-assistant) and the [Threat Hunting](incident-response.md#threat-hunting) in-scope asset inventory, so automated reasoning knows a host's real external attack surface.

---

## Vulnerability Management

Track and remediate CVEs across the estate.

- **Vulnerability snapshots** — periodic counts of Critical/High/Medium/Low findings per organisation, trended over time on the vulnerability dashboard.
- **CVE advisories** — fetches remediation guidance from Ubuntu Security and Microsoft MSRC for CVEs found in the estate (Ubuntu and Windows platforms supported).
- **Work packages** — group related vulnerabilities into a tracked remediation effort with per-item status (Open · In Progress · Resolved · Accepted Risk).
- **Risk acceptance** — formally accept a CVE with a justification; accepted risks are surfaced separately and do not pollute the active queue.

---

## App Ingress (Reverse Proxy & WAF)

Let customers safely publish their own services to the internet without manual infrastructure work.

- **Self-service route management** — create ingress routes mapping a public FQDN to any backend host:port, scoped to the organisation.
- **Automatic SSL termination** — BunkerWeb provisions and renews Let's Encrypt certificates automatically; the creation form shows the DNS A-record target and a background check warns if DNS is not yet aligned.
- **Structured 7-tab settings UI** — the route settings panel is organised into dedicated tabs: General, WAF, IP Whitelist, Rate Limiting, Country, Bot Protection, and Advanced. Each tab has its own Save button with an unsaved-changes indicator dot and per-tab toast feedback.
- **General tab** — edit backend host, port, and protocol after creation; FQDN is displayed read-only.
- **Web Application Firewall** — ModSecurity with the OWASP Core Rule Set protects every route. Paranoia level (1–4) is shown as a segmented control with a description per level; HTTPS redirect can be toggled per route.
- **IP Whitelist** — add allowed IPs and CIDRs as a chip list with inline validation; capped at 10 entries with a clear limit message.
- **Rate limiting** — structured number + unit input (`r/s`, `r/m`, `r/h`) guards against traffic spikes and credential-stuffing.
- **Country access controls** — searchable multi-select popover lets operators block or allow countries by name rather than memorising ISO codes.
- **Bot protection** — toggle antibot challenge per route; choose the challenge type (cookie, JavaScript, reCAPTCHA, hCaptcha, Turnstile) with conditional credential fields per provider.
- **Advanced tab** — configure upstream proxy timeouts (connect, read, send), WebSocket proxying, proxy buffering, maximum request body size, allowed HTTP methods, real-IP extraction headers, and full CORS settings.
- **Blocked activity reports** — live feed of blocked requests (source IP, rule triggered, action taken) fetched on demand from BunkerWeb.
- Routes support both direct (public IP) and NetBird (overlay network) backend types.
- **Backend host picker** — a route can be explicitly linked to the Host Asset it fronts. The link drives the host's derived [internet-facing status](#fleet--asset-management) and lets analysts link a route to an incident to automatically pull in the asset behind it.
