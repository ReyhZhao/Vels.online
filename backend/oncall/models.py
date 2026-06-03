import zoneinfo

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


def validate_iana_timezone(value):
    if value not in zoneinfo.available_timezones():
        raise ValidationError(f"'{value}' is not a valid IANA timezone.")


class StaffProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    timezone = models.CharField(max_length=64, default="Europe/Amsterdam", validators=[validate_iana_timezone])

    def __str__(self):
        return f"StaffProfile({self.user})"


class ShiftBlock(models.Model):
    """A named time block within a 24-hour day, e.g. Morning (06:00–14:00)."""
    label = models.CharField(max_length=64)
    start_time = models.TimeField()
    end_time = models.TimeField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.label} ({self.start_time}–{self.end_time})"


class RotationTemplateSlot(models.Model):
    """Default analyst assignment for a (day_of_week, shift_block) pair."""

    day_of_week = models.IntegerField()  # 0=Mon, 6=Sun
    shift_block = models.ForeignKey(ShiftBlock, on_delete=models.CASCADE, related_name="template_slots")
    analyst = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="template_slots"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["day_of_week", "shift_block"], name="unique_dow_block")
        ]

    def __str__(self):
        return f"RotationTemplateSlot(dow={self.day_of_week}, block={self.shift_block}, analyst={self.analyst})"


class ShiftOverride(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
    ]

    KIND_SWAP = "swap"
    KIND_COVER_OFFER = "cover_offer"
    KIND_CHOICES = [
        (KIND_SWAP, "Swap"),
        (KIND_COVER_OFFER, "Cover Offer"),
    ]

    date = models.DateField()
    shift_block = models.ForeignKey(ShiftBlock, on_delete=models.CASCADE, related_name="overrides")
    original_analyst = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="original_overrides"
    )
    override_analyst = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="override_overrides"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_SWAP)
    initiated_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="initiated_overrides"
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"ShiftOverride({self.date}, {self.shift_block}, {self.status})"


def _block_minute_intervals(block):
    """Return (start, end) minute pairs for a block, splitting midnight-crossing blocks."""
    start = block.start_time.hour * 60 + block.start_time.minute
    end_h = block.end_time.hour * 60 + block.end_time.minute
    end = end_h if end_h != 0 else 1440
    if end <= start:
        return [(start, 1440), (0, end)]
    return [(start, end)]


def validate_tiling(exclude_pk=None):
    """Check that no ShiftBlocks overlap in time.

    Blocks may cover any duration and are not required to tile a full 24 hours.
    Gaps in coverage are allowed; overlapping blocks are not.
    """
    qs = ShiftBlock.objects.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    blocks = list(qs)

    for i, a in enumerate(blocks):
        a_ivs = _block_minute_intervals(a)
        for b in blocks[i + 1:]:
            b_ivs = _block_minute_intervals(b)
            for a_start, a_end in a_ivs:
                for b_start, b_end in b_ivs:
                    if a_start < b_end and b_start < a_end:
                        raise ValidationError(
                            f"Shift blocks '{a.label}' and '{b.label}' overlap."
                        )
