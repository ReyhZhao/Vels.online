from django.db import transaction


def next_alert_display_id():
    from alerts.models import Alert

    with transaction.atomic():
        last = (
            Alert.objects.select_for_update()
            .filter(display_id__startswith="AL-")
            .order_by("-display_id")
            .first()
        )
        if last:
            last_seq = int(last.display_id.split("-")[-1])
            seq = last_seq + 1
        else:
            seq = 1
        return f"AL-{seq:04d}"
