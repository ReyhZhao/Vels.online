import re
from urllib.parse import urlparse

from ioc_finder import find_iocs

_SOC_RE = re.compile(r"^soc[@+]", re.IGNORECASE)


def _is_soc_address(address: str) -> bool:
    local = address.split("@")[0]
    return bool(_SOC_RE.match(local + "@"))


def _owned_assets(organization):
    """Return (owned_ips, owned_domains) sets for the given organization."""
    from incidents.models import Asset

    qs = Asset.objects.filter(organization=organization, is_active=True)

    owned_ips = set(
        qs.filter(ip_address__isnull=False)
        .values_list("ip_address", flat=True)
    )

    owned_domains = set(
        qs.filter(kind=Asset.KIND_ROUTE, route__isnull=False)
        .values_list("route__fqdn", flat=True)
    )

    return owned_ips, owned_domains


def _url_hostname(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def extract_and_save_iocs(incident):
    from incidents.models import IOC

    owned_ips, owned_domains = _owned_assets(incident.organization)

    text = f"{incident.title}\n{incident.description}"
    found = find_iocs(text)

    iocs = []
    for ip in found.get("ipv4s", []):
        if ip not in owned_ips:
            iocs.append(IOC(incident=incident, kind=IOC.KIND_IP, value=ip))
    for ip in found.get("ipv6s", []):
        if ip not in owned_ips:
            iocs.append(IOC(incident=incident, kind=IOC.KIND_IP, value=ip))
    for domain in found.get("domains", []):
        if domain.lower() not in owned_domains:
            iocs.append(IOC(incident=incident, kind=IOC.KIND_DOMAIN, value=domain))
    for url in found.get("urls", []):
        if _url_hostname(url).lower() not in owned_domains:
            iocs.append(IOC(incident=incident, kind=IOC.KIND_URL, value=url))

    if incident.source_kind == "inbound_email":
        iocs.extend(_extract_email_iocs(incident, found))

    if iocs:
        IOC.objects.bulk_create(iocs, ignore_conflicts=True)


def _extract_email_iocs(incident, found_in_text):
    from incidents.models import IOC

    source_ref = incident.source_ref or {}
    forwarder_address = (source_ref.get("forwarder_address") or "").lower()

    seen = set()
    iocs = []

    def _add(address):
        addr = address.strip().lower()
        if not addr or addr in seen:
            return
        if forwarder_address and addr == forwarder_address:
            return
        if _is_soc_address(addr):
            return
        seen.add(addr)
        iocs.append(IOC(incident=incident, kind=IOC.KIND_EMAIL, value=addr))

    sender = source_ref.get("sender_address")
    if sender:
        _add(sender)

    for addr in found_in_text.get("email_addresses", []):
        _add(addr)

    return iocs
