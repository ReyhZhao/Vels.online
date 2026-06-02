from datetime import datetime, time

from django.contrib.auth.models import User


def get_oncall_analyst(at: datetime) -> User | None:
    """Resolve who is on-call at the given UTC-aware datetime.

    Resolution order:
    1. Accepted ShiftOverride for that date+block
    2. RotationTemplateSlot for that dow+block
    3. None (gap)
    """
    if at.tzinfo is None:
        raise ValueError("'at' must be timezone-aware (UTC).")

    from oncall.models import ShiftBlock, RotationTemplateSlot

    # Find which ShiftBlock covers this time
    current_time = at.time().replace(second=0, microsecond=0)
    block = _find_block(current_time)
    if block is None:
        return None

    date = at.date()
    dow = at.weekday()  # 0=Mon, 6=Sun

    # 1. Check for accepted ShiftOverride
    try:
        from oncall.models import ShiftOverride
        override = ShiftOverride.objects.filter(
            date=date,
            shift_block=block,
            status="accepted",
        ).select_related("override_analyst").first()
        if override is not None:
            return override.override_analyst
    except Exception:
        pass  # ShiftOverride not yet defined or import error

    # 2. Check rotation template
    try:
        slot = RotationTemplateSlot.objects.select_related("analyst").get(
            day_of_week=dow,
            shift_block=block,
        )
        return slot.analyst
    except RotationTemplateSlot.DoesNotExist:
        return None


def _find_block(current_time: time):
    """Return the ShiftBlock that covers current_time, or None."""
    from oncall.models import ShiftBlock

    for block in ShiftBlock.objects.all():
        start = block.start_time
        end = block.end_time

        if end == time(0, 0):
            # Midnight-crossing block: end is 00:00 meaning midnight
            if current_time >= start or current_time < time(0, 1):
                return block
            # More general: covers start..23:59 and 00:00..just_before_midnight
            if current_time >= start:
                return block
        elif end > start:
            # Normal block: start <= time < end
            if start <= current_time < end:
                return block
        else:
            # Midnight-crossing (end < start)
            if current_time >= start or current_time < end:
                return block

    return None
