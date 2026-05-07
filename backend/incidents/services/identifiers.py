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
