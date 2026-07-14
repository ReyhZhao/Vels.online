# Contact incident notifications reuse the customer Audience floor; closure is tiered by TLP

## Status

accepted

## Context

The platform already messages a **Contact** — a named human at a customer org — *about* an
**Incident** in two ways: a **question** (analyst asks, reply is imported) and a one-way
**closure notification** (#388). We are reworking the notification side so an **Incident
Contact** can opt into either **closure-only** (default) or **all-updates**, and so the
emails carry *usable* content (the recent comment, or an LLM closure summary) instead of the
generic "we wanted to inform you" card the current `contact_notified` template renders — a
template that, today, does not even show the message body it is given.

The open question was the **disclosure floor**: an email to a Contact is a customer-facing
channel, arguably *more* external than the in-app org-member view. The platform already has
a canonical customer floor — `filter_comments_for_user` / the **Audience** concept — and it
is stricter than the "non-internal, non-TLP-red" the feature was first framed with: an org
member sees non-internal comments **only at TLP:WHITE/GREEN**, and **nothing at AMBER or
RED**. Meanwhile incident *fields* (id/title/description) follow `can_view_incident`, which
blocks only RED. The default incident TLP is **AMBER**, and the default Contact preference is
**closure-only**, so a naïve "same gate for everything" makes the common case send nothing.

## Decision

Contact notifications **never exceed the customer Audience floor** — an email must never
contain content the customer cannot already see in their own portal. Concretely:

- **All-updates** fires only for a newly-created, **non-internal `user` comment** on a
  **TLP:WHITE/GREEN** Incident — one email per comment. There is no AMBER-safe variant: the
  update body *is* a comment, which is hidden from customers at AMBER.
- **Closure** is **tiered by TLP**, reconciling the two floors (fields vs comment content):
  **RED → nothing** (the customer cannot see the Incident at all); **AMBER → a bare
  "resolved" notice** (id/title/description + closure reason, *no* summary); **WHITE/GREEN →
  a full LLM-generated closure summary**. This tightens today's behavior, where closure
  fires at *any* TLP including RED.
- The **closure summary** is synthesised from the Incident's **non-internal comments plus its
  AI-triage comments** — triage is a *named exception* to the internal filter, because it is
  the investigation narrative and without it there is nothing of substance to tell the
  customer. Every *other* internal comment (analyst notes, internal task summaries) stays
  out. Raw triage text is *input* to the LLM, never emitted verbatim; the WHITE/GREEN gate
  plus a customer-safe prompt are the guards.

Supporting choices: the preference lives on **`IncidentContact`** (per-incident, not a global
Contact trait — appetite tracks *this* incident's relevance); attribution is **generic** ("your
security team"), never the individual analyst; notifications are **one-way** (no `reply_to` —
the **question** flow remains the two-way channel); and both kinds are recorded as
`ContactMessage` rows (updates under a new `update` role, closure under the existing
`notified`) so the SOC has a durable record of exactly what a Contact received.

## Considered options

- **The literal "non-internal, non-TLP-red" framing** (email at AMBER too). Rejected: it
  emails a Contact content the platform deliberately hides from that same customer in-app —
  a channel that defeats the Audience floor.
- **One flat WHITE/GREEN gate for closure as well.** Rejected: with default-AMBER incidents
  and default closure-only contacts, the feature would send *nothing* in the common case.
  The tiered split keeps the "your incident is resolved" courtesy useful at AMBER without
  leaking comment-derived content.
- **Excluding triage from the summary** (non-internal comments only, honouring the flag
  literally). Rejected: triage is where the investigation actually lives; without it the
  summary is empty. A dedicated "customer-safe" flag on triage comments is the cleaner long-
  term answer but is out of scope for v1.

## Consequences

- `is_internal` gains a third reasoning context ("does this reach a Contact?"), alongside its
  existing customer-portal and partner-sync meanings — but AI-triage is the one deliberate
  exception, so the flag is not the *sole* gate for the closure summary.
- All-updates is **inert by default**: an analyst must set an Incident to WHITE/GREEN before
  any update email fires. This is intended — notifying a Contact about ongoing activity *is* a
  disclosure act and should require a conscious customer-shareable TLP.
- Today's closure notification is **tightened**: incidents at AMBER lose the LLM summary
  (bare notice only) and RED incidents stop notifying entirely.
- Residual risk: a triage comment can carry internal specifics that a paraphrased summary
  might surface. Accepted for v1 under the same trust model as #388 (LLM prompt + TLP gate).
