import re

from ioc_finder import find_iocs

_SOC_RE = re.compile(r"^soc[@+]", re.IGNORECASE)


def _is_soc_address(address: str) -> bool:
    local = address.split("@")[0]
    return bool(_SOC_RE.match(local + "@"))


def extract_and_save_iocs(incident):
    from incidents.models import IOC

    text = f"{incident.title}\n{incident.description}"
    found = find_iocs(text)

    iocs = []
    for ip in found.get("ipv4s", []):
        iocs.append(IOC(incident=incident, kind=IOC.KIND_IP, value=ip))
    for ip in found.get("ipv6s", []):
        iocs.append(IOC(incident=incident, kind=IOC.KIND_IP, value=ip))
    for domain in found.get("domains", []):
        iocs.append(IOC(incident=incident, kind=IOC.KIND_DOMAIN, value=domain))
    for url in found.get("urls", []):
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
