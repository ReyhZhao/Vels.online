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


def validate_tiling(exclude_pk=None):
    """Check that all ShiftBlocks together cover exactly 24h with no gaps or overlaps.

    Blocks can start at any time; the check is circular (wraps around midnight).
    """
    qs = ShiftBlock.objects.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    blocks = list(qs.order_by("order"))

    if not blocks:
        raise ValidationError("At least one shift block is required for 24/7 coverage.")

    # Build intervals in minutes. Expand midnight-crossing blocks.
    # Each interval is (start_minutes, end_minutes) with end > start.
    # end_time==00:00 means midnight = 1440 minutes.
    intervals = []
    for b in blocks:
        start = b.start_time.hour * 60 + b.start_time.minute
        end_h = b.end_time.hour * 60 + b.end_time.minute
        end = end_h if end_h != 0 else 1440
        if end <= start:
            end += 1440  # midnight crossing
        intervals.append((start, end))

    total = sum(e - s for s, e in intervals)
    if total != 1440:
        raise ValidationError(
            f"Shift blocks must cover exactly 24 hours. Currently covering {total} minutes."
        )

    # Sort by start time and check for gaps/overlaps in a circular sense.
    # We normalise all intervals relative to the first block's start.
    intervals.sort(key=lambda x: x[0])
    first_start = intervals[0][0]

    # Re-express all intervals relative to first_start, modulo 1440
    normalised = []
    for start, end in intervals:
        s = (start - first_start) % 1440
        e = s + (end - start)
        normalised.append((s, e))

    normalised.sort(key=lambda x: x[0])

    current = 0
    for start, end in normalised:
        if start > current:
            raise ValidationError(
                f"Gap detected in shift coverage (at +{start} minutes from first block start)."
            )
        if start < current:
            raise ValidationError(
                f"Overlap detected in shift coverage (at +{start} minutes from first block start)."
            )
        current = end

    if current != 1440:
        raise ValidationError(
            f"Shift blocks do not cover the full 24 hours (ends at +{current} minutes)."
        )
