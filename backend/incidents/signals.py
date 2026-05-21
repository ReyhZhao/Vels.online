from django.db.models.signals import post_save
from django.dispatch import receiver

from incidents.tasks import acquire_triage_lock, run_incident_triage


@receiver(post_save, sender="incidents.Incident")
def enqueue_triage_on_new_incident(sender, instance, created, **kwargs):
    if not created or instance.state != "new":
        return

    if acquire_triage_lock(instance.id):
        run_incident_triage.delay(instance.id)
