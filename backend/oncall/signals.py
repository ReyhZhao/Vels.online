from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_staff_profile(sender, instance, **kwargs):
    if instance.is_staff:
        from oncall.models import StaffProfile
        StaffProfile.objects.get_or_create(user=instance)
