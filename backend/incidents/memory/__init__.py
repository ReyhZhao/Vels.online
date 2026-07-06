"""Self-learning Triage memory (PRD #659, ADR-0030/0031).

Two complementary mechanisms feed the existing Triage harness:

- **Precedent** (``precedents``): richer retrieval of resolved same-org Incidents,
  injected at the cheap Classify phase. Strictly per-tenant (ADR-0031).
- **Triage Lesson** (``lessons``): distilled, subject-keyed disposition heuristics,
  applied at the gated Work phase. Informs, never fires.

Learning is disciplined by ``distillation`` (the batched sweep) and ``corrections``
(the misclassification feedback loop); ``review`` is the staff-only proposed→active gate.
"""
