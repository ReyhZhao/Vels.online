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


def _auto_link_routes_for_asset(asset):
    """Scan this org's unlinked routes and auto-link any with an unambiguous IP match."""
    from ingress.models import Route
    from ingress.services.backend_match import match_backend_to_asset

    unlinked = list(Route.objects.filter(organization=asset.organization, backend_asset__isnull=True))
    for route in unlinked:
        auto_match, _ = match_backend_to_asset(route, [asset])
        if auto_match:
            route.backend_asset = asset
            route.save(update_fields=["backend_asset"])


@receiver(post_save, sender="incidents.Asset")
def auto_link_asset_to_routes(sender, instance, created, update_fields, **kwargs):
    if instance.kind != "host":
        return
    if not created and update_fields and "ip_address" not in update_fields:
        return
    _auto_link_routes_for_asset(instance)


@receiver(post_save, sender="ingress.Route")
def auto_link_route_to_asset(sender, instance, created, **kwargs):
    if instance.backend_asset_id is not None:
        return

    from incidents.models import Asset
    from ingress.services.backend_match import match_backend_to_asset

    candidates = list(
        Asset.objects.filter(organization=instance.organization, kind="host")
    )
    auto_match, _ = match_backend_to_asset(instance, candidates)
    if auto_match:
        instance.backend_asset = auto_match
        instance.save(update_fields=["backend_asset"])
