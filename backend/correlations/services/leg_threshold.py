"""Pure predicate for a Leg's document-count threshold (#519, ADR-0020).

The single source of truth for whether a Scheduled Search Rule Leg is satisfied by
the number of documents that matched it. Both evaluation paths (single-leg and
multi-leg) call this so the `gte`/`lte` semantics can never drift apart again.

`gte` (default) is the ordinary "at least N matched" detection; `lte` is an Absence
Firing ("at most N matched", e.g. ≤ 0 = "no documents in the window").
"""
from correlations.models import SEARCH_COUNT_OP_LTE


def count_satisfies(matched_count: int, operator: str, threshold: int) -> bool:
    """True when *matched_count* satisfies the leg's count *threshold* under *operator*.

    Any operator other than `lte` is treated as the default `gte`, so legacy legs and
    unknown values keep the historical "at least" behaviour.
    """
    if operator == SEARCH_COUNT_OP_LTE:
        return matched_count <= threshold
    return matched_count >= threshold
