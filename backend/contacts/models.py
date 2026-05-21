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
    ROLE_NOTIFIED = "notified"
    ROLE_QUESTIONED = "questioned"
    ROLE_CHOICES = [
        (ROLE_NOTIFIED, "Notified"),
        (ROLE_QUESTIONED, "Questioned"),
    ]

    incident = models.ForeignKey("incidents.Incident", on_delete=models.CASCADE, related_name="incident_contacts")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="incident_contacts")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_NOTIFIED)
    message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("incident", "contact")]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.contact} on {self.incident} ({self.role})"
