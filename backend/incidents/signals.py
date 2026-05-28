from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from incidents.tasks import acquire_triage_lock, enrich_iocs_then_triage


@receiver(post_save, sender="incidents.Incident")
def enqueue_triage_on_new_incident(sender, instance, created, **kwargs):
    if not created or instance.state != "new":
        return

    if acquire_triage_lock(instance.id):
        incident_id = instance.id
        transaction.on_commit(lambda: enrich_iocs_then_triage.delay(incident_id))
