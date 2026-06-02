from django.utils import timezone

from oncall.models import ShiftOverride


def request_swap(date, shift_block, original_analyst, override_analyst, initiated_by, note="", kind="swap") -> ShiftOverride:
    """Create a pending ShiftOverride request and notify the recipient."""
    override = ShiftOverride.objects.create(
        date=date,
        shift_block=shift_block,
        original_analyst=original_analyst,
        override_analyst=override_analyst,
        initiated_by=initiated_by,
        note=note,
        kind=kind,
        status=ShiftOverride.STATUS_PENDING,
    )
    _notify_swap(override, event="requested")
    return override


def accept_override(override: ShiftOverride, actor) -> ShiftOverride:
    """Accept an override. Only the override_analyst may accept."""
    if override.status != ShiftOverride.STATUS_PENDING:
        raise ValueError(f"Cannot accept an override with status '{override.status}'.")
    if actor.pk != override.override_analyst_id:
        raise ValueError("Only the override analyst may accept this request.")
    override.status = ShiftOverride.STATUS_ACCEPTED
    override.resolved_at = timezone.now()
    override.save(update_fields=["status", "resolved_at"])
    _notify_swap(override, event="accepted")
    return override


def decline_override(override: ShiftOverride, actor) -> ShiftOverride:
    """Decline an override. Only the override_analyst may decline."""
    if override.status != ShiftOverride.STATUS_PENDING:
        raise ValueError(f"Cannot decline an override with status '{override.status}'.")
    if actor.pk != override.override_analyst_id:
        raise ValueError("Only the override analyst may decline this request.")
    override.status = ShiftOverride.STATUS_DECLINED
    override.resolved_at = timezone.now()
    override.save(update_fields=["status", "resolved_at"])
    _notify_swap(override, event="declined")
    return override


def _notify_swap(override: ShiftOverride, event: str):
    """Send shift_swap notification to relevant parties."""
    try:
        from notifications.services.notifications import notify

        initiator_name = (
            override.initiated_by.get_full_name() or override.initiated_by.username
        )
        block_label = override.shift_block.label
        date_str = override.date.isoformat()
        kind_label = "swap" if override.kind == ShiftOverride.KIND_SWAP else "cover offer"

        if event == "requested":
            # Notify the override_analyst (person being asked)
            notify(
                "shift_swap",
                [override.override_analyst],
                incident=None,
                payload={
                    "title": f"Shift {kind_label} request from {initiator_name}",
                    "body": f"{initiator_name} has requested a {kind_label} for {block_label} on {date_str}.",
                    "link": "/admin/incidents/oncall",
                    "override_id": override.pk,
                },
            )
        elif event == "accepted":
            notify(
                "shift_swap",
                [override.initiated_by],
                incident=None,
                payload={
                    "title": "Shift swap accepted",
                    "body": f"Your {kind_label} request for {block_label} on {date_str} has been accepted.",
                    "link": "/admin/incidents/oncall",
                    "override_id": override.pk,
                },
            )
        elif event == "declined":
            notify(
                "shift_swap",
                [override.initiated_by],
                incident=None,
                payload={
                    "title": "Shift swap declined",
                    "body": f"Your {kind_label} request for {block_label} on {date_str} has been declined.",
                    "link": "/admin/incidents/oncall",
                    "override_id": override.pk,
                },
            )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Failed to send shift_swap notification", exc_info=True)
