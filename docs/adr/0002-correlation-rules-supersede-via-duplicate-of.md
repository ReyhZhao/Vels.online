# Correlation rules supersede simpler incidents via `duplicate_of`

When a Correlation Rule fires and a contributing alert already belongs to an
incident created by the synchronous fast-path (severity promote / asset
threshold), the richer multi-leg "chain" incident wins. For v1 we supersede
**light**: relink the alerts onto the chain incident, then mark the absorbed
incident `duplicate_of` the chain incident and close it `CLOSURE_DUPLICATE`.
We do **not** physically migrate the absorbed incident's tasks/comments/assignee
(A-deep); its history stays on the closed incident, reachable via the pointer,
and the supersede is reversible.

## Considered Options

- **A-light via `duplicate_of` (chosen)** — reuses existing primitives, non-destructive, reversible.
- **A-deep record merge** — moves tasks/IOCs/comments onto the chain incident; correct but heavy, forces conflict resolution (two assignees, two task lists), effectively irreversible.
- **Link-don't-create (no supersede)** — simplest, but the canonical incident keeps the weaker "single alert" framing instead of the chain narrative.

## Consequences

- **Guard rail:** an incident a human is actively working (`in_progress`/`on_hold`/assigned) is NOT auto-superseded — it is flagged for human confirmation instead, so work is never yanked out from under an analyst.
- Two engines run side by side in v1 (synchronous fast-path + async correlation); the supersede rule is what keeps them from producing divergent duplicate incidents.
