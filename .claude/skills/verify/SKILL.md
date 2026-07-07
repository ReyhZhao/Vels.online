---
name: verify
description: How to drive and observe this app end-to-end for verification — launch handles, auth notes, browser-driving recipe.
---

# Verifying vels.online changes

The stack is Docker Compose and is usually already up (`docker compose ps`):
frontend (Vite) on http://localhost:5173, backend (Django) on
http://localhost:8000, plus postgres + valkey. Both containers mount the
source, so edits hot-reload — no rebuild needed to observe a change.

## API surface

Local dev has `DEV_AUTO_LOGIN` middleware: plain `curl http://localhost:8000/api/...`
is already authenticated **as a staff user**. Non-staff paths can't be curled
this way — cover those with the pytest suite instead.

## Browser surface

No Playwright in the repo, but a Playwright chromium build is cached at
`~/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app`.
Recipe: `npm install playwright-core` in the scratchpad, then
`chromium.launch({ executablePath: <cached binary>, headless: true })` and
drive http://localhost:5173. Auto-login applies in the browser too — no login
flow needed.

Worth capturing on UI changes: fullPage screenshot at 1440px, a 375px-wide
mobile shot plus `document.documentElement.scrollWidth === clientWidth`
(no-horizontal-scroll invariant), and any drill-down navigation URLs.

## Gotchas

- `/api/security/dashboard/` (and other Wazuh/OpenSearch-backed endpoints)
  return 5xx locally — no Wazuh instance in dev. UIs are expected to degrade
  to "—"; don't count those console errors as findings.
- 3 backend tests fail only under local Docker (status cache + alert 401);
  they pass in CI — see memory `reference_local_test_flakes.md`.
- Tests: `docker compose exec -T backend pytest -q`,
  `docker compose exec -T frontend npm test -- <file>`.
