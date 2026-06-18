"""Derive internet-facing exposure data for a host Asset (PRD #536).

``host_exposures`` returns a unified list of Exposure value objects without
hitting any model internals — callers (serialiser, LLM tools, Hunt inventory)
use the same contract.

``annotate_internet_facing`` annotates a queryset with a boolean so list
views can both display and filter in a single query.
"""
from dataclasses import dataclass
from typing import Dict, List, Literal

from django.db.models import Exists, OuterRef, QuerySet


@dataclass
class Exposure:
    kind: Literal["ingress_route", "direct_nat"]
    protection: Literal["protected", "raw"]
    specifics: Dict


def host_exposures(asset) -> List[Exposure]:
    from ingress.models import Route
    from incidents.models import NatExposure

    result: List[Exposure] = []

    for route in Route.objects.filter(backend_asset=asset):
        result.append(Exposure(
            kind="ingress_route",
            protection="protected",
            specifics={"fqdn": route.fqdn, "backend_port": route.backend_port},
        ))

    for nat in NatExposure.objects.filter(asset=asset):
        result.append(Exposure(
            kind="direct_nat",
            protection="raw",
            specifics={
                "protocol": nat.protocol,
                "port": nat.port,
                "public_ip": str(nat.public_ip) if nat.public_ip else None,
                "description": nat.description or None,
                "id": nat.pk,
            },
        ))

    return result


def annotate_internet_facing(qs: QuerySet) -> QuerySet:
    from ingress.models import Route
    from incidents.models import NatExposure

    has_route = Exists(Route.objects.filter(backend_asset=OuterRef("pk")))
    has_nat = Exists(NatExposure.objects.filter(asset=OuterRef("pk")))
    return qs.annotate(internet_facing=has_route | has_nat)
