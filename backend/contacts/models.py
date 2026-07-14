from django.db import models


class Contact(models.Model):
    organisation = models.ForeignKey(
        "security.Organization", on_delete=models.CASCADE, related_name="contacts"
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    job_title = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("organisation", "email")]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class AssetOwner(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="asset_ownerships")
    asset = models.ForeignKey("incidents.Asset", on_delete=models.CASCADE, related_name="asset_ownerships")

    class Meta:
        unique_together = [("contact", "asset")]

    def __str__(self):
        return f"{self.contact} owns {self.asset}"


class IncidentContact(models.Model):
    # Per-incident notification level (ADR-0034). closure_only is the default so an
    # existing link keeps today's behaviour (notified once, on close); all_updates
    # additionally emails the contact when an analyst posts a customer-facing comment.
    NOTIFY_CLOSURE_ONLY = "closure_only"
    NOTIFY_ALL_UPDATES = "all_updates"
    NOTIFY_LEVEL_CHOICES = [
        (NOTIFY_CLOSURE_ONLY, "Closure only"),
        (NOTIFY_ALL_UPDATES, "All updates"),
    ]

    incident = models.ForeignKey("incidents.Incident", on_delete=models.CASCADE, related_name="incident_contacts")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="incident_contacts")
    notify_level = models.CharField(
        max_length=20, choices=NOTIFY_LEVEL_CHOICES, default=NOTIFY_CLOSURE_ONLY
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("incident", "contact")]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.contact} on {self.incident}"


class ContactMessage(models.Model):
    DIRECTION_OUTBOUND = "outbound"
    DIRECTION_INBOUND = "inbound"
    DIRECTION_CHOICES = [
        (DIRECTION_OUTBOUND, "Outbound"),
        (DIRECTION_INBOUND, "Inbound"),
    ]
    ROLE_NOTIFIED = "notified"
    ROLE_QUESTIONED = "questioned"
    ROLE_UPDATE = "update"
    ROLE_CHOICES = [
        (ROLE_NOTIFIED, "Notified"),
        (ROLE_QUESTIONED, "Questioned"),
        (ROLE_UPDATE, "Update"),
    ]

    incident = models.ForeignKey("incidents.Incident", on_delete=models.CASCADE, related_name="contact_messages")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="contact_messages")
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, blank=True)
    body = models.TextField()
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies"
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.direction} message from {self.contact} on {self.incident}"
