from django.db import transaction

from .models import FreedRuleId, WazuhRuleIdPool


def allocate_rule_id():
    """Return the next available Wazuh rule ID from the pool.

    Reuses IDs from FreedRuleId before incrementing the counter.
    Raises ValueError if the pool (200000–209999) is exhausted.
    """
    with transaction.atomic():
        freed = FreedRuleId.objects.select_for_update().order_by("rule_id").first()
        if freed:
            rule_id = freed.rule_id
            freed.delete()
            return rule_id

        pool = WazuhRuleIdPool.objects.select_for_update().first()
        if pool is None:
            raise ValueError("WazuhRuleIdPool has not been seeded.")
        next_id = pool.last_assigned_id + 1
        if next_id > WazuhRuleIdPool.POOL_MAX:
            raise ValueError(
                f"Wazuh rule ID pool exhausted "
                f"({WazuhRuleIdPool.POOL_MIN}–{WazuhRuleIdPool.POOL_MAX})."
            )
        pool.last_assigned_id = next_id
        pool.save(update_fields=["last_assigned_id"])
        return next_id


def free_rule_id(rule_id):
    """Return a rule ID to the pool for future reuse."""
    FreedRuleId.objects.get_or_create(rule_id=rule_id)
