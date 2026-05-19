from django.contrib.auth.models import User
from django.db import models

from incidents.models import Incident, Task


class EmailTemplate(models.Model):
    NAMES = [
        ("notification_digest", "Notification Digest"),
        ("incident_digest", "Incident Digest"),
        ("invite", "Account Invitation"),
        ("rejection", "Signup Rejection"),
        ("signup_request", "New Signup Request (Admin)"),
        ("test", "Test Email"),
    ]

    name = models.CharField(max_length=60, unique=True, choices=NAMES)
    subject = models.CharField(max_length=255)
    html_body = models.TextField()
    description = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_name_display()


class NotificationPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="notification_preferences")
    email_assignment = models.BooleanField(default=True)
    inapp_assignment = models.BooleanField(default=True)
    email_delegation = models.BooleanField(default=True)
    inapp_delegation = models.BooleanField(default=True)
    email_comment = models.BooleanField(default=True)
    inapp_comment = models.BooleanField(default=True)
    email_state_change = models.BooleanField(default=True)
    inapp_state_change = models.BooleanField(default=True)
    email_incident_alert = models.BooleanField(default=True)
    inapp_incident_alert = models.BooleanField(default=True)
    email_system_alert = models.BooleanField(default=True)
    inapp_system_alert = models.BooleanField(default=True)
    email_task_complete = models.BooleanField(default=False)
    inapp_task_complete = models.BooleanField(default=True)
    push_assignment = models.BooleanField(default=False)
    push_delegation = models.BooleanField(default=False)
    push_comment = models.BooleanField(default=False)
    push_state_change = models.BooleanField(default=False)
    push_incident_alert = models.BooleanField(default=False)
    push_task_complete = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"NotificationPreferences({self.user})"


class PushSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PushSubscription({self.user}, {self.endpoint[:40]}…)"


class Notification(models.Model):
    KIND_ASSIGNMENT = "assignment"
    KIND_DELEGATION = "delegation"
    KIND_COMMENT = "comment"
    KIND_STATE_CHANGE = "state_change"
    KIND_INCIDENT_ALERT = "incident_alert"
    KIND_SYSTEM_ALERT = "system_alert"
    KIND_TASK_COMPLETE = "task_complete"
    KIND_CHOICES = [
        (KIND_ASSIGNMENT, "Assignment"),
        (KIND_DELEGATION, "Delegation"),
        (KIND_COMMENT, "Comment"),
        (KIND_STATE_CHANGE, "State Change"),
        (KIND_INCIDENT_ALERT, "Incident Alert"),
        (KIND_SYSTEM_ALERT, "System Alert"),
        (KIND_TASK_COMPLETE, "Task Complete"),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    task = models.ForeignKey(
        Task, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications"
    )
    payload = models.JSONField(default=dict)
    shown_inapp = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "read_at"]),
            models.Index(fields=["recipient", "incident", "email_sent_at"]),
        ]

    def __str__(self):
        return f"Notification({self.kind}) for {self.recipient}"
