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
