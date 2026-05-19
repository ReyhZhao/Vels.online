from ioc_finder import find_iocs


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

    if iocs:
        IOC.objects.bulk_create(iocs, ignore_conflicts=True)