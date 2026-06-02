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
