from django.db import models


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
    invite_token = models.UUIDField(null=True, blank=True)  # Authentik invitation pk (used in URL and for deletion)
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
