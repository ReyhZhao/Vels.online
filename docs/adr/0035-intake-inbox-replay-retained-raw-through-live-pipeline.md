# Intake Inbox replay: retained raw `.eml` re-run through the live partner pipeline

## Status

accepted

## Context

The v1 **Intake Inbox** (ADR-0032) is a dead-letter surface: inbound mail that reached
the SOC mailbox but no handler accepted. Its "Create Connection" action onboards a
partner **going forward only** — a report the partner sent *before* onboarding is lost.
Issue #667 asks that, when a **Connection** is created for that sender, the already-held
message(s) be **replayed** so the missed **Incident** actually gets created and held
follow-ups **thread** onto it.

Two facts shape the design:

- The Intake Inbox v1 stores **bounded metadata only** (a 500-char body excerpt), not the
  raw message. Replay needs the raw `.eml` — the same bytes the live pipeline verifies,
  maps, and matches on.
- The inbound router checks the partner handler **before** phishing, but only when a
  Connection already matches the sender. An un-onboarded partner emailing `soc@` therefore
  falls through to the **phishing** handler, which drops a non-forwarded report as
  `phishing:dropped:not_forward`. So the *primary* would-be-partner case dead-letters under
  a **phishing** drop reason, not `dropped:unrecognised_to`. Drop reason is a poor
  predictor of "is this a replayable partner message".

## Decision

**Retain the raw `.eml` for *all* terminal drops**, stored via `StorageClient` under a
dedicated `intake-inbox/{id}/…` prefix (never in the DB), referenced by a nullable
`raw_s3_key` on the row. Raw and row share the **one** `PARTNER_INTAKE_RETENTION_DAYS`
window; the purge deletes the object *then* the row, so replay is only possible inside the
retention window and no malware outlives its metadata.

**Gate the replay *offer* on sender-set membership of an active Connection**, not on drop
reason. Whatever reason a partner's mail dropped under, the bytes are there; the replay
affordance appears only once a staff-vetted Connection covers that sender (a spammer never
gets one). Retention scope and replay-offer scope are deliberately separate.

**Replay reuses the live pipeline verbatim.** A Connection-scoped
`GET/POST /api/partners/connections/{id}/replay-intake/` endpoint feeds each held row's raw
bytes straight into `PartnerIngestionHandler.handle(...)` — the **same** DKIM/SPF gate,
field-mapping, and `(connection, External Reference)` matching as live intake. There is no
"trusted replay" bypass: an unknown-sender drop was never verification-tested, so replay is
its first pass through the gate; a message that cannot pass **stays dead-lettered**.

**Scope is the whole held backlog for the Connection's sender set, oldest-first**
(`received_at` asc), so a create precedes its updates and threading works via the same
matching. Idempotency is per-row: `replayed_at` + `replayed_incident` mark completed rows,
replay skips already-marked rows (so a mid-batch failure *resumes*), and
`select_for_update(skip_locked=True)` serialises concurrent runs. On success the intake raw
object is deleted (the bytes now live as an attachment on the incident), shrinking
malware-at-rest to only *un*-replayed mail. The `GET` preview **dry-runs the mapping** and
shows the per-message extracted External Reference, so staff see whether the backlog will
thread into one incident or fragment into several *before* committing (warn, not block).

## Considered options

- **Keep retention narrow (only `dropped:unrecognised_to`) / fix the router to dead-letter
  would-be-partner mail under a distinct reason.** Rejected: the router's phishing-first
  flow means the primary case is `phishing:dropped:not_forward`, indistinguishable from
  spam at capture; narrowing retention by drop reason would discard exactly the messages
  replay exists to recover, and re-routing risks regressing the phishing path. Broad
  retention + Connection-gated *offer* is robust to the routing quirk.
- **Trust the original capture verdict at replay (no re-verification).** Rejected: an
  unknown-sender drop was never verified, so there is no verdict to trust; re-running the
  standard gate on the retained raw is both cheap and the only safe stance against a
  spoofed From that merely happened to be un-routable.
- **Single-message (row-scoped) replay.** Rejected: a report plus follow-ups sit as
  separate rows; replaying one leaves the others unthreaded. Whole-backlog oldest-first is
  the only ordering that reproduces the sequence the SOC actually received.
- **Separate raw-retention knob / longer raw window.** Rejected: a single shared window
  keeps the malware-at-rest promise legible — "gone in N days, bytes and all".

## Consequences

- The SOC now warehouses raw spam/phishing payloads for every terminal drop for the
  retention window — the PII / malware-at-rest cost issue #667 anticipated. Bounded by the
  shared purge and an isolated storage prefix ops can lifecycle-rule or scan separately.
- Replay has a **time bound**: onboard the partner within the retention window or the held
  message is purged and unreplayable.
- A replayed message can still *fail* verification (`PARTNER_INTAKE_VERIFY_AUTH` on by
  default) even right after onboarding, if that sender's mail never carried a passing
  `Authentication-Results` — it stays in the Intake Inbox, correctly.
- A Connection with a blank `external_reference_regex` fragments a multi-message backlog
  into several flagged incidents; the preview surfaces this but does not prevent it.
