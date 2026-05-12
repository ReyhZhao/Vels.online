import socket

from celery import shared_task
from django.conf import settings


@shared_task
def push_route_settings(fqdn, settings_dict):
    from .bunkerweb import BunkerWebClient, BunkerWebError
    from .models import Route

    try:
        route = Route.objects.get(fqdn=fqdn)
    except Route.DoesNotExist:
        return

    try:
        BunkerWebClient().update_service_settings(fqdn, settings_dict)
    except BunkerWebError:
        route.status = Route.STATUS_ERROR
        route.save(update_fields=["status"])


@shared_task
def check_route_dns(route_id):
    from .models import Route

    try:
        route = Route.objects.get(pk=route_id)
    except Route.DoesNotExist:
        return

    expected_ip = getattr(settings, "BUNKERWEB_PUBLIC_IP", "")

    try:
        resolved_ip = socket.gethostbyname(route.fqdn)
        dns_ok = resolved_ip == expected_ip
    except OSError:
        dns_ok = False

    route.dns_ok = dns_ok
    route.save(update_fields=["dns_ok"])
