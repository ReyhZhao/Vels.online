import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone

INVITE_TTL_DAYS = 7


class InvalidTransition(Exception):
    pass


class SignupRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_EXPIRED = "expired"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_COMPLETED, "Completed"),
    ]

    email = models.EmailField()
    full_name = models.CharField(max_length=255)
    org_name = models.CharField(max_length=255)
    intended_use = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # Set at approval time (possibly edited by staff)
    approved_org_name = models.CharField(max_length=255, blank=True)
    org_slug = models.SlugField(max_length=255, blank=True)

    # Authentik provisioning state
    authentik_group_pk = models.CharField(max_length=255, blank=True)
    invite_token = models.UUIDField(null=True, blank=True)
    invite_expires_at = models.DateTimeField(null=True, blank=True)

    # Rejection details
    rejection_reason = models.CharField(max_length=255, blank=True)
    rejection_note = models.TextField(blank=True)
    send_rejection_email = models.BooleanField(default=True)

    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    actioned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.email} ({self.status})"

    # ── State machine ─────────────────────────────────────────────────────────

    def _require_status(self, *expected):
        if self.status not in expected:
            raise InvalidTransition(
                f"Cannot transition from '{self.status}' — "
                f"expected one of: {', '.join(expected)}"
            )

    def approve(self, org_name, org_slug, group_pk, invite_token_value):
        """pending → approved. Sets provisioning fields and a 7-day invite expiry."""
        self._require_status(self.STATUS_PENDING)
        self.status = self.STATUS_APPROVED
        self.approved_org_name = org_name
        self.org_slug = org_slug
        self.authentik_group_pk = group_pk
        self.invite_token = invite_token_value
        self.invite_expires_at = timezone.now() + timedelta(days=INVITE_TTL_DAYS)
        self.actioned_at = timezone.now()

    def reject(self, reason, note="", send_email=True):
        """pending → rejected."""
        self._require_status(self.STATUS_PENDING)
        self.status = self.STATUS_REJECTED
        self.rejection_reason = reason
        self.rejection_note = note
        self.send_rejection_email = send_email
        self.actioned_at = timezone.now()

    def complete(self):
        """approved → completed. Triggered automatically on first login."""
        self._require_status(self.STATUS_APPROVED)
        self.status = self.STATUS_COMPLETED

    def expire(self):
        """approved → expired. Run by the nightly Celery beat task."""
        self._require_status(self.STATUS_APPROVED)
        self.status = self.STATUS_EXPIRED

    def resend(self, invite_token_value):
        """expired → approved. Generates a fresh invite token and resets expiry."""
        self._require_status(self.STATUS_EXPIRED)
        self.status = self.STATUS_APPROVED
        self.invite_token = invite_token_value
        self.invite_expires_at = timezone.now() + timedelta(days=INVITE_TTL_DAYS)
        self.actioned_at = timezone.now()
