from django.db import models


class Route(models.Model):
    PROTOCOL_HTTP = "http"
    PROTOCOL_HTTPS = "https"
    PROTOCOL_CHOICES = [
        (PROTOCOL_HTTP, "HTTP"),
        (PROTOCOL_HTTPS, "HTTPS"),
    ]

    TYPE_DIRECT = "direct"
    TYPE_NETBIRD = "netbird"
    TYPE_CHOICES = [
        (TYPE_DIRECT, "Direct"),
        (TYPE_NETBIRD, "NetBird"),
    ]

    STATUS_PENDING = "pending"
    STATUS_ACTIVE = "active"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_ERROR, "Error"),
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    fqdn = models.CharField(max_length=255, unique=True)
    backend_host = models.CharField(max_length=255)
    backend_port = models.PositiveIntegerField()
    backend_protocol = models.CharField(max_length=5, choices=PROTOCOL_CHOICES, default=PROTOCOL_HTTP)
    backend_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_DIRECT)
    organization = models.ForeignKey(
        "security.Organization", on_delete=models.CASCADE, related_name="routes"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    dns_ok = models.BooleanField(null=True, blank=True)
    backend_asset = models.ForeignKey(
        "incidents.Asset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="route_exposures",
        limit_choices_to={"kind": "host"},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.fqdn
