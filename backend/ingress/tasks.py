import socket

from celery import shared_task
from django.conf import settings


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
