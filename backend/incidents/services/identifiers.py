from django.db import transaction
from django.utils import timezone


def next_display_id():
    from incidents.models import Incident

    year = timezone.now().year
    prefix = f"INC-{year}-"

    with transaction.atomic():
        last = (
            Incident.objects.select_for_update()
            .filter(display_id__startswith=prefix)
            .order_by("-display_id")
            .first()
        )
        if last:
            last_seq = int(last.display_id.split("-")[-1])
            seq = last_seq + 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"


def next_report_reference_id():
    from incidents.models import Report

    year = timezone.now().year
    prefix = f"REP-{year}-"

    with transaction.atomic():
        last = (
            Report.objects.select_for_update()
            .filter(reference_id__startswith=prefix)
            .order_by("-reference_id")
            .first()
        )
        if last:
            seq = int(last.reference_id.split("-")[-1]) + 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"
