"""In-depth handbook content served only to authenticated users.

The public handbook lives in the frontend bundle (siteContent.js) and is
readable by anyone. This deeper reference — the detection-engineering material
for Scheduled Search Rules — is deliberately *not* bundled: it is returned by an
authenticated API endpoint so it never ships to logged-out visitors.

Prose, not data: it is versioned with the code that renders it, so a copy change
is a normal deploy. Article bodies are markdown. `icon` names must exist in the
frontend CONTENT_ICONS map.

Screenshot insertion points are marked with a `> 🖼️ **Screenshot:** …`
blockquote until the real images are captured and dropped in as markdown.
"""

EXTENDED_DOC_SECTIONS = [
    {
        "id": "ssr-core",
        "icon": "Radar",
        "title": "Scheduled Search Rules — in depth",
        "summary": "The pull engine: what it is, how a rule is shaped, and how a match becomes an incident.",
        "articles": [
            {
                "id": "pull-engine",
                "title": "The pull engine",
                "body": [
                    "A **Scheduled Search Rule** is a rule that, on a schedule, pushes its pattern-match *down into* the Wazuh **OpenSearch** backend to detect a pattern of raw Wazuh events — **without** ingesting the whole stream into the platform. It runs as a periodic per-organisation background task, queries the raw indices directly, and only pulls matching documents into the app when it triggers.",
                    "It is deliberately the mirror image of a **Correlation Rule**, and the two should never be conflated:",
                    "- **Correlation rules evaluate by *push*.** A signal has to arrive as an ingested alert first; the rule reacts in (near) real time to alerts moving through the streaming engine, matching over the normalised **entity envelope** (`host.name`, `source.ip`, …).\n- **Scheduled search rules evaluate by *pull*.** Nothing has to be ingested first. On each run the rule queries the raw Wazuh document schema directly (`wazuh-alerts-*`, and IT-Hygiene inventory state in `wazuh-states-inventory-*`), and there are **no in-app alert rows at all until the rule triggers**.",
                    "This is what lets a scheduled search rule reach detections a correlation rule structurally cannot: the vast majority of Wazuh events are never promoted to platform alerts, so they are invisible to the push engine. A pull rule sees the full stream.",
                    "Do not confuse a Scheduled Search Rule with a **Hunt**, either. A Hunt is interactive, staff-initiated, and open-ended; a Scheduled Search Rule is its opposite — non-interactive, scheduled, and running the same query on a fixed cadence. If the goal is to *explore*, that is a Hunt; if the goal is to *watch for a known pattern forever*, that is a Scheduled Search Rule.",
                    "**Tenant isolation is absolute.** Every query is scoped to a single organisation's Wazuh agents (`agent.id` ∈ that org's `wazuh_group` members). A rule's **window** and **correlation key** join *never* cross tenants — even a `correlation_key = none` rule correlates only within one org's agent scope. A **system rule** achieves this by fanning out **per organisation** at run time (skipping any org that has muted it), so it is really N isolated evaluations, not one shared one.",
                ],
            },
            {
                "id": "anatomy",
                "title": "Anatomy of a rule",
                "body": [
                    "A rule is a small stack of settings plus one or more **legs**. Everything below is set in the authoring drawer.",
                    "> 🖼️ **Screenshot:** the full authoring drawer — rule details on the left, legs on the right.",
                    "**Rule-level settings**\n- **Name / Description** — what it detects, in human terms.\n- **Correlation key** — the entity the legs bind on: `none` (org-wide), `host.name`, `source.ip`, `user.name`, `file.hash.sha256`, or `process.name`. `none` means “correlate across everything in this org” and is typically used with a single leg.\n- **Severity** — the severity of the incident the rule raises.\n- **Window (minutes)** — the rolling span within which *all* legs must be satisfied for the same key.\n- **Interval (minutes)** — how often the rule runs (minimum 5). Independent of the window.\n- **Baseline lookback (days)** — history depth for **novelty** legs (see Advanced constraints). Ignored if no leg uses novelty.\n- **Max findings / run** — a cap on how many matched documents a single run will pull in.\n- **Enabled** — whether the schedule is live.\n- **Include agentless events** — see the dedicated article.",
                    "**Legs and conditions.** A **leg** matches a *class* of Wazuh document. Each leg carries:\n- one or more **conditions** — a `field_name` (a raw Wazuh field such as `rule.id` or `data.srcip`), an **operator** (`equals`, `contains`, `>=`, `<=`, or `IP in CIDR`), and a `value`. All conditions on a leg must hold for a document to match the leg.\n- a **count** with a **count operator** (`≥` by default, or `≤` for an absence firing) — the document-count threshold the leg must clear.\n- optionally a **diversity** or **novelty** constraint (Advanced constraints).",
                    "**Window vs. interval — keep them straight.** The *interval* is how often the rule wakes up; the *window* is how far back each run looks. They are set independently. A 60-minute window on a 15-minute interval means each run re-examines the last hour, so a persisting condition is re-seen on consecutive runs (the dedup ledger, below, stops that from spawning duplicate incidents). A window **shorter** than the interval leaves gaps between runs; a window **longer** than the interval overlaps. Choose deliberately.",
                    "**Match semantics are co-occurrence, not sequence.** When a rule has several legs, “satisfied” means *all legs are present for the same key within the window* — **not** “leg A then leg B” in order. Strict ordering is a recognised future axis and is deliberately not supported today; if a detection depends on ordering, encode what you can as co-occurrence and note the limitation.",
                ],
            },
            {
                "id": "match-to-incident",
                "title": "From match to incident",
                "body": [
                    "When a rule triggers, each raw Wazuh document its query matched is a **Finding**. Findings are what the rule pulls into the platform — and *only* the matches are pulled, never the whole index.",
                    "Each Finding is **materialised** into an in-app alert at trigger time: this is the bridge that lets a pull rule reuse the entire existing incident / IOC / triage pipeline, all of which assume real alert rows. A materialised search-alert is **born-linked and suppressed** — created with `source_kind = scheduled_search`, already attached to the rule's incident, and deliberately kept *out* of the streaming engine (it neither triggers streaming evaluation nor is scanned by other rules' windows). So a scheduled-search finding participates only in its own rule's incident and never seeds cross-source correlation.",
                    "All of a run's Findings together produce **one incident**, which itself carries `source_kind = scheduled_search`, keeping it outside the streaming supersede logic.",
                    "**Deduplication.** At most one *live* (open-incident) firing exists per `(rule, key value)`. While that firing is live, further matching documents fold into the **same** open incident rather than spawning a new one; a fresh firing for that key only becomes possible once the incident closes. This is why a long-running condition — or an overlapping window — does not bury you in duplicate incidents. Every firing is recorded in a `SearchFiring` ledger row.",
                    "> 🖼️ **Screenshot:** the firing badge / firing history on a rule in the admin list.",
                    "**Absence is the exception.** An **absence firing** (a `≤` leg — see Advanced constraints) has *nothing* to materialise: there are no matched documents. It still produces an incident, but one with **no linked alerts** — the shortfall itself is the evidence, carried in the incident description and the ledger.",
                ],
            },
            {
                "id": "system-and-org",
                "title": "System rules, org rules, and muting",
                "body": [
                    "Scheduled Search Rules use the same two tiers as Correlation Rules:",
                    "- **System rule** (`organization = null`) — authored centrally, applied to every tenant as baseline detection. At run time it **fans out per organisation**, evaluating each org in isolation and **skipping any org that has muted it**.\n- **Org rule** (`organization` set) — scoped to one tenant, evaluating only against that org's data.",
                    "The tier is set with the **scope selector** in the authoring drawer: *All organizations — System Rule*, or a specific organisation — *Org Rule*.",
                    "> 🖼️ **Screenshot:** the scope selector in the authoring drawer.",
                    "**Muting is per-(rule, org) and staff-driven.** A tenant cannot mute a rule for themselves; a SOC analyst mutes a noisy system rule *on their behalf* from the org-system-rules view (it records a `SearchRuleMute` for that rule + organisation pair, and the fan-out then skips them). Muting never edits or disables the rule for anyone else — it is a per-tenant suppression, fully reversible.",
                    "Because a system rule is really N isolated per-org evaluations, a mute for one tenant has no effect on any other, and a per-org failure during fan-out is isolated — one org erroring does not stop the others from being evaluated.",
                ],
            },
        ],
    },
    {
        "id": "ssr-constraints",
        "icon": "SlidersHorizontal",
        "title": "Advanced constraints",
        "summary": "The leg-level axes beyond a plain count: absence, diversity, novelty, time-of-day, and agentless.",
        "articles": [
            {
                "id": "count-operators",
                "title": "Count operators & absence firings",
                "body": [
                    "Every leg carries a **count operator** governing how its document-count threshold is compared:",
                    "- **`≥` (gte)** — the default. “At least N documents matched.” Ordinary presence detection.\n- **`≤` (lte)** — the inverse. The leg is satisfied when *at most* N documents matched. `≤ 0` is the common case: “no matching documents at all.” This is an **absence firing**.",
                    "An absence firing is how you detect a *silence* — a thing that should be happening and stopped. The canonical example is “no firewall logs received in the last hour”: a device that goes quiet is often the first sign of a problem, and a plain `≥` rule can never catch it because there is nothing to match on.",
                    "> 🖼️ **Screenshot:** a leg with the count operator set to ≤ 0, showing the absence-firing explainer.",
                    "**An absence firing produces no Findings and no alerts.** There is nothing to materialise — the shortfall *is* the evidence, carried in the incident description and a `SearchFiring` row. It still rides the normal incident and triage pipeline, and it reuses the one-live-incident-per-`(rule, key)` dedup, so a persisting silence folds into the open incident instead of raising one per run.",
                    "**Absence is only supported for `correlation_key = none`.** A terms aggregation can enumerate the keys that *did* appear, but it cannot enumerate the keys that went silent — there is no universe of “expected” keys to compare against. A rule that combines `≤` with a correlation key is **rejected at save time**, and the drawer flags it before you can save.",
                ],
            },
            {
                "id": "diversity",
                "title": "Diversity constraints",
                "body": [
                    "A **diversity constraint** is an extra requirement on a leg: its matching documents, **grouped by the rule's correlation key**, must span at least **M distinct values** of a chosen field. It is evaluated *alongside* the leg's count threshold — both must hold for the leg to be satisfied for a key.",
                    "It expresses **“spread across N different X,”** which a plain count cannot: a count only knows *how many* documents matched, not how many *distinct* values of some field they carried.",
                    "The motivating case is **impossible-travel-lite**: several successful logins for one user, originating from two or more different countries, inside the window. You set `correlation_key = user.name`, a leg matching successful authentications, and a diversity constraint of *distinct `GeoLocation.country_name` ≥ 2*.",
                    "> 🖼️ **Screenshot:** the diversity row on a leg (distinct field + ≥ N).",
                    "**A diversity constraint requires a correlation key** (not `none`) — it needs something to group by. The drawer flags this if the key is left on `none`.",
                    "Diversity is **pure set-cardinality within the window**. It has no notion of history and no notion of geography or distance — it counts distinct values, full stop. If you need “distance ÷ time” physics, that is a separate future axis; if you need “new compared to the past,” you want a **novelty constraint** instead.",
                ],
            },
            {
                "id": "novelty",
                "title": "Novelty constraints",
                "body": [
                    "A **novelty constraint** fires on a value the engine **has not seen before**. Grouped by the correlation key, the leg is satisfied for a key only when a matching document carries a value of the leg's chosen **novelty field** whose *earliest* occurrence within the **baseline lookback** falls **inside the window** — i.e. the value is appearing for the first time in recorded history.",
                    "It is the **baseline-comparing sibling** of diversity. Where diversity counts distinct values *within* the window (no history), novelty compares the window *against* the baseline lookback to surface values that are **new to history**. It is the engine's first axis that reaches outside a single rolling window.",
                    "The motivating case is **a user logging onto a host that is new *for them***: `correlation_key = user.name`, novelty field `host.name`. The **baseline lookback (days)** rule setting controls how far back “seen before” reaches — a larger lookback approaches “ever.”",
                    "> 🖼️ **Screenshot:** the novelty row on a leg (first-seen field) plus the baseline-lookback setting.",
                    "**How it is evaluated.** Statelessly, as a single pushed-down OpenSearch aggregation (a terms-of-terms with a `min(@timestamp)` sub-aggregation over the baseline). That means it works correctly on a rule's **very first run** with no warm-up period, and it stores no per-entity state in the platform.",
                    "**Constraints.** A novelty leg **requires a correlation key** (not `none`) to group by, and it **cannot** be combined with the `≤` (absence) operator. The drawer enforces both.",
                ],
            },
            {
                "id": "time-of-day",
                "title": "Time-of-day windows",
                "body": [
                    "A rule can optionally restrict matches to — or *away from* — certain hours of the day and days of the week, evaluated in the **organisation's timezone**.",
                    "You set a **start** time, an **end** time, a set of **days**, and a **mode**:\n- **Inside** — only match during these hours/days.\n- **Outside** — only match *outside* these hours/days.",
                    "The classic use is “outside working hours”: set the business-hours window and mode *Outside*, so a detection only fires when the activity happens at a suspicious time. If a start and end time are set, at least one day must be chosen, or the window must be cleared.",
                    "> 🖼️ **Screenshot:** the time-of-day window controls (start/end, day chips, mode).",
                    "This can be set by hand, or by just asking the AI assistant — “only outside working hours” — and it will fill the fields in. Leave it empty for no time constraint.",
                ],
            },
            {
                "id": "agentless",
                "title": "Agentless events",
                "body": [
                    "By default a rule only matches events tied to a registered Wazuh **agent** in the organisation's scope. Some of the most valuable telemetry, though, comes from infrastructure that is *not* an agent — a reverse proxy, a firewall, other perimeter devices.",
                    "**Include agentless events** broadens a rule to match those events too. It is **off by default**, because most detections are host-centric and perimeter noise should not leak in; turn it on deliberately when the pattern being watched for lives in infrastructure logs.",
                    "> 🖼️ **Screenshot:** the “Include agentless events” toggle and its helper text.",
                    "The firewall-silence absence firing is the archetype that needs this on: the logs being watched for the *absence* of are agentless, so without this toggle the rule has nothing to look at.",
                ],
            },
        ],
    },
    {
        "id": "ssr-authoring",
        "icon": "Sparkles",
        "title": "Authoring workflow",
        "summary": "Drafting with AI, testing a rule before it goes live, and three worked examples.",
        "articles": [
            {
                "id": "drafting-with-ai",
                "title": "Drafting with AI",
                "body": [
                    "The **Draft with AI** drawer turns a natural-language description into a ready-to-edit rule. It is a **two-pass** flow: the assistant first selects the relevant Wazuh rules for what was described, then drafts the conditions, correlation key, window, and any constraints from them.",
                    "> 🖼️ **Screenshot:** the AI drafting drawer — conversation on the left, live draft on the right.",
                    "A few things worth knowing about how it behaves:\n- **Pick the scope first.** The scope selector both sets the tier (system vs. org rule) *and* grounds the draft in that scope's recent alerts, so the assistant proposes fields that actually occur in the data.\n- **It is a conversation.** Each message replays the whole thread plus the current draft; follow up to refine (“make the window 30 minutes”, “only outside working hours”, “add a diversity constraint on country”) and the draft updates in place.\n- **Warnings and the tool trace.** The drawer surfaces warnings (e.g. a field it could not find) and a `🔎` trace of what the assistant did each turn — read them, they catch mistakes early.\n- **Review before saving.** The assistant drafts; it never activates a rule. Nothing is persisted until **Save rule** is pressed, and every field remains editable by hand.",
                    "The assistant may also search the internet for threat intelligence to inform what to detect, so a description like “detect the persistence technique from <threat report>” can produce a sensible starting point.",
                ],
            },
            {
                "id": "testing",
                "title": "Testing a rule before it goes live",
                "body": [
                    "A **Rule Test** is a named, saved test attached to one Scheduled Search Rule — the detection-as-code “unit test” for that rule. It bundles a set of **sample documents** and a single **expectation**, and is run on demand to check whether the rule still behaves as its author intended. A rule can have as many tests as you like.",
                    "> 🖼️ **Screenshot:** the Rule Tests drawer with a passing and a failing test.",
                    "A Rule Test asserts the **whole rule's external behaviour** — *does it fire?* — never a leg or a condition in isolation. The **expectation** is simply “fires” or “does not fire” against the bundled sample documents. Running a test produces a **test result**: pass/fail, plus **diagnostics** explaining *why* (which leg fell short, which key satisfied or missed, a diversity shortfall). The diagnostics are explanatory only — they are not additional assertions you author.",
                    "Tests run against an **ephemeral, real OpenSearch index** — the samples are indexed and the actual rule query is run against them — so a test exercises the same query path production uses, not a reimplementation of it. This is what makes it safe to tune a noisy rule for one tenant: a change can be proven not to have blunted the detection the rule was built for.",
                    "The rule list shows a **test-health badge** per rule (passing / failing / never-run), so a rule whose tests have gone red is visible at a glance.",
                    "**Debug Run** is the complementary tool: where a Rule Test runs the rule against *sample* documents you control, a Debug Run executes it against *recent live data* to see what it would actually match right now — the fastest way to sanity-check a fresh draft before enabling it.",
                    "> 🖼️ **Screenshot:** a Debug Run result showing matched documents.",
                ],
            },
            {
                "id": "worked-examples",
                "title": "Worked examples",
                "body": [
                    "Three end-to-end detections that each exercise a different axis. Exact field names depend on the decoders in the environment — treat the values below as representative.",
                    "**1 — Impossible-travel-lite (diversity).** *“The same user signs in successfully from two or more countries within an hour.”*\n- **Correlation key:** `user.name`\n- **Window / interval:** 60 min / 15 min\n- **Leg:** conditions matching successful authentications (e.g. `rule.groups` *contains* `authentication_success`), count `≥ 1`, **diversity:** distinct `GeoLocation.country_name` `≥ 2`\n- **Severity:** high\n\nThe count alone would fire on any successful login; the diversity constraint is what turns it into “from *different countries*.”",
                    "**2 — First host for a user (novelty).** *“A user authenticates to a host they have never used before.”*\n- **Correlation key:** `user.name`\n- **Baseline lookback:** 90 days\n- **Window / interval:** 60 min / 30 min\n- **Leg:** conditions matching successful authentications, count `≥ 1`, **novelty:** first-seen `host.name`\n\nNo warm-up is needed — the novelty aggregation looks back over the 90-day baseline on the very first run.",
                    "**3 — Firewall gone silent (absence).** *“No firewall logs received in the last hour.”*\n- **Correlation key:** `none` (required for absence)\n- **Window / interval:** 60 min / 15 min\n- **Include agentless events:** on (the firewall is not a Wazuh agent)\n- **Leg:** conditions identifying firewall log documents, count operator `≤`, count `0`\n- **Severity:** high\n\nThis one fires precisely *because* nothing matched, and the incident it raises carries no evidence alerts — the silence is the finding.",
                    "Each of these should ship with at least one **Rule Test** (a small bundle of sample documents that should, and should not, trigger it) before it is enabled.",
                ],
            },
        ],
    },
]
