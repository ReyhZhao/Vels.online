import re

_PLACEHOLDER_RE = re.compile(r"\{\{([^{}]{1,64})\}\}")

_SUPPORTED = {
    "incident.id",
    "incident.display_id",
    "asset.ip",
    "ioc.ip",
    "ioc.domain",
}


def _resolve_placeholder(name, incident):
    """Return the string value for a single placeholder name, or None if unresolvable."""
    name = name.strip()
    if name == "incident.id":
        return str(incident.id)
    if name == "incident.display_id":
        return str(incident.display_id)
    if name == "asset.ip":
        asset = incident.assets.filter(ip_address__isnull=False).first()
        return str(asset.ip_address) if asset and asset.ip_address else None
    if name == "ioc.ip":
        ioc = incident.iocs.filter(kind="ip").first()
        return str(ioc.value) if ioc else None
    if name == "ioc.domain":
        ioc = incident.iocs.filter(kind="domain").first()
        return str(ioc.value) if ioc else None
    return None


def interpolate_args(template, incident):
    """Resolve {{placeholder}} in template against incident context.

    Unresolvable placeholders are left unchanged (as-is).
    Returns the interpolated string.
    """
    if not template:
        return template

    def replace(m):
        value = _resolve_placeholder(m.group(1), incident)
        return value if value is not None else m.group(0)

    return _PLACEHOLDER_RE.sub(replace, template)
