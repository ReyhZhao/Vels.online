import ipaddress
import json
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


def _parse_internal_networks(organization):
    """Parse the org's declared internal CIDR ranges into ip_network objects (#603).

    Bad entries are skipped defensively — the serializer validates on write, but a
    row could predate that or be edited out-of-band; extraction must never raise.
    """
    networks = []
    for entry in (getattr(organization, "internal_ip_ranges", None) or []):
        try:
            networks.append(ipaddress.ip_network((entry or "").strip(), strict=False))
        except ValueError:
            continue
    return networks


def _owned_domain_suffixes(organization):
    """Return the org's declared owned domains, lower-cased (#603)."""
    return [
        d.strip().lower().rstrip(".")
        for d in (getattr(organization, "owned_domains", None) or [])
        if (d or "").strip()
    ]


def _ip_in_internal_ranges(value: str, networks) -> bool:
    if not networks:
        return False
    try:
        addr = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    return any(addr in net for net in networks)


def _domain_is_owned(domain: str, suffixes) -> bool:
    """True if `domain` equals or is a subdomain of any owned suffix.

    Case-insensitive, and guards the partial-label trap: `evilexample.com` is NOT
    matched by `example.com` (only a `.`-boundary or exact match counts).
    """
    if not domain or not suffixes:
        return False
    candidate = domain.strip().lower().rstrip(".")
    for suffix in suffixes:
        if candidate == suffix or candidate.endswith("." + suffix):
            return True
    return False


def _url_hostname(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def _alert_evidence_text(incident) -> str:
    """Collect IOC-bearing evidence from an incident's linked Alerts (#601).

    Some incidents carry their indicators on the linked Alerts rather than in the
    incident title/description — notably scheduled-search incidents, whose title/description
    are a generated rule summary. Each Alert's raw `source_ref` (the Wazuh `_source` doc,
    e.g. data.srcip/data.dstip/data.url) and its normalised entity envelope are flattened
    into a text blob so find_iocs can surface them. Benefits any incident whose evidence
    lives on its alerts, not just scheduled-search.
    """
    alerts_rel = getattr(incident, "alerts", None)
    if alerts_rel is None:
        return ""

    parts = []
    for alert in alerts_rel.all().prefetch_related("entities"):
        source_ref = alert.source_ref
        if isinstance(source_ref, dict) and source_ref:
            try:
                parts.append(json.dumps(source_ref, default=str))
            except (TypeError, ValueError):
                pass
        for entity in alert.entities.all():
            if entity.value:
                parts.append(entity.value)
    return "\n".join(parts)


def extract_and_save_iocs(incident):
    from incidents.models import IOC

    org = incident.organization
    owned_ips, owned_domains = _owned_assets(org)
    internal_networks = _parse_internal_networks(org)
    owned_suffixes = _owned_domain_suffixes(org)

    def _is_owned_ip(ip):
        return ip in owned_ips or _ip_in_internal_ranges(ip, internal_networks)

    def _is_owned_domain(domain):
        return domain.lower() in owned_domains or _domain_is_owned(domain, owned_suffixes)

    text = f"{incident.title}\n{incident.description}\n{_alert_evidence_text(incident)}"
    found = find_iocs(text)

    iocs = []
    for ip in found.get("ipv4s", []):
        if not _is_owned_ip(ip):
            iocs.append(IOC(incident=incident, kind=IOC.KIND_IP, value=ip))
    for ip in found.get("ipv6s", []):
        if not _is_owned_ip(ip):
            iocs.append(IOC(incident=incident, kind=IOC.KIND_IP, value=ip))
    for domain in found.get("domains", []):
        if not _is_owned_domain(domain):
            iocs.append(IOC(incident=incident, kind=IOC.KIND_DOMAIN, value=domain))
    for url in found.get("urls", []):
        if not _is_owned_domain(_url_hostname(url)):
            iocs.append(IOC(incident=incident, kind=IOC.KIND_URL, value=url))

    if incident.source_kind == "inbound_email":
        iocs.extend(_extract_email_iocs(incident, found, owned_suffixes))

    if iocs:
        IOC.objects.bulk_create(iocs, ignore_conflicts=True)


def _extract_email_iocs(incident, found_in_text, owned_suffixes=None):
    from incidents.models import IOC

    owned_suffixes = owned_suffixes or []
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
        domain_part = addr.split("@", 1)[-1] if "@" in addr else ""
        if _domain_is_owned(domain_part, owned_suffixes):
            return
        seen.add(addr)
        iocs.append(IOC(incident=incident, kind=IOC.KIND_EMAIL, value=addr))

    sender = source_ref.get("sender_address")
    if sender:
        _add(sender)

    for addr in found_in_text.get("email_addresses", []):
        _add(addr)

    return iocs
