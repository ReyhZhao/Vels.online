import datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone as tz
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RotationTemplateSlot, ShiftBlock, StaffProfile, validate_tiling
from .serializers import (
    RotationTemplateSlotSerializer,
    RotationTemplateSlotWriteSerializer,
    ShiftBlockSerializer,
    StaffProfileSerializer,
)


class StaffProfileView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        profile, _ = StaffProfile.objects.get_or_create(user=request.user)
        return Response(StaffProfileSerializer(profile).data)

    def patch(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        profile, _ = StaffProfile.objects.get_or_create(user=request.user)
        serializer = StaffProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ShiftBlockListView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        blocks = ShiftBlock.objects.all().order_by("order")
        return Response(ShiftBlockSerializer(blocks, many=True).data)

    def post(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        if not request.user.is_superuser:
            return Response(status=403)
        serializer = ShiftBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                block = serializer.save()
                validate_tiling()
        except DjangoValidationError as exc:
            return Response({"detail": exc.message}, status=400)
        return Response(ShiftBlockSerializer(block).data, status=201)


class ShiftBlockDetailView(APIView):
    def _get_block(self, pk):
        try:
            return ShiftBlock.objects.get(pk=pk), None
        except ShiftBlock.DoesNotExist:
            return None, Response(status=404)

    def patch(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        if not request.user.is_superuser:
            return Response(status=403)
        block, err = self._get_block(pk)
        if err:
            return err
        serializer = ShiftBlockSerializer(block, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                block = serializer.save()
                validate_tiling()
        except DjangoValidationError as exc:
            return Response({"detail": exc.message}, status=400)
        return Response(ShiftBlockSerializer(block).data)

    def delete(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        if not request.user.is_superuser:
            return Response(status=403)
        block, err = self._get_block(pk)
        if err:
            return err
        try:
            with transaction.atomic():
                block.delete()
                validate_tiling(exclude_pk=pk)
        except DjangoValidationError as exc:
            return Response({"detail": exc.message}, status=400)
        return Response(status=204)


class RotationTemplateView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        slots = RotationTemplateSlot.objects.select_related("analyst", "shift_block").all()
        return Response(RotationTemplateSlotSerializer(slots, many=True).data)

    def put(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        if not request.user.is_superuser:
            return Response(status=403)
        if not isinstance(request.data, list):
            return Response({"detail": "Expected a list of slot objects."}, status=400)

        serializers_list = [RotationTemplateSlotWriteSerializer(data=item) for item in request.data]
        errors = []
        for i, s in enumerate(serializers_list):
            if not s.is_valid():
                errors.append({str(i): s.errors})
        if errors:
            return Response(errors, status=400)

        with transaction.atomic():
            RotationTemplateSlot.objects.all().delete()
            created = []
            for s in serializers_list:
                data = s.validated_data
                slot = RotationTemplateSlot.objects.create(
                    day_of_week=data["day_of_week"],
                    shift_block_id=data["shift_block_id"],
                    analyst_id=data.get("analyst_id"),
                )
                created.append(slot)

        slots = RotationTemplateSlot.objects.select_related("analyst", "shift_block").filter(
            pk__in=[s.pk for s in created]
        )
        return Response(RotationTemplateSlotSerializer(slots, many=True).data)


class CurrentOnCallView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)

        from oncall.services.resolver import get_oncall_analyst, _find_block
        now = tz.now()
        analyst = get_oncall_analyst(at=now)
        block = _find_block(now.time().replace(second=0, microsecond=0))

        if analyst is None:
            return Response({"analyst": None})

        # Calculate shift end time in UTC
        shift_end_utc = None
        if block:
            end_time = block.end_time
            if end_time == datetime.time(0, 0):
                # Midnight
                tomorrow = now.date() + datetime.timedelta(days=1)
                shift_end_utc = datetime.datetime.combine(
                    tomorrow, datetime.time(0, 0), tzinfo=datetime.timezone.utc
                ).isoformat()
            else:
                shift_end_utc = datetime.datetime.combine(
                    now.date(), end_time, tzinfo=datetime.timezone.utc
                ).isoformat()

        return Response({
            "analyst": {
                "id": analyst.id,
                "name": analyst.get_full_name() or analyst.username,
                "username": analyst.username,
            },
            "shift_block": {
                "id": block.id,
                "label": block.label,
            } if block else None,
            "shift_end_utc": shift_end_utc,
        })


class OnCallScheduleWeekView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)

        week_param = request.query_params.get("week")
        if not week_param:
            now = tz.now()
            year, week, _ = now.isocalendar()
            week_param = f"{year}-W{week:02d}"

        try:
            year_str, week_str = week_param.split("-W")
            year = int(year_str)
            week_num = int(week_str)
        except (ValueError, AttributeError):
            return Response({"detail": "Invalid week format. Use YYYY-WNN."}, status=400)

        # Get the Monday of that week
        import datetime as dt
        monday = dt.date.fromisocalendar(year, week_num, 1)

        blocks = list(ShiftBlock.objects.all().order_by("order"))
        slots = {
            (s.day_of_week, s.shift_block_id): s
            for s in RotationTemplateSlot.objects.select_related("analyst", "shift_block").all()
        }

        # Fetch overrides for the week
        try:
            from oncall.models import ShiftOverride
            week_dates = [monday + dt.timedelta(days=i) for i in range(7)]
            overrides = {
                (o.date, o.shift_block_id): o
                for o in ShiftOverride.objects.filter(
                    date__in=week_dates,
                    status__in=["accepted", "pending"],
                ).select_related("override_analyst", "original_analyst")
            }
        except Exception:
            overrides = {}

        result = []
        for day_offset in range(7):
            day_date = monday + dt.timedelta(days=day_offset)
            dow = day_date.weekday()
            for block in blocks:
                slot = slots.get((dow, block.id))
                override = overrides.get((day_date, block.id))
                accepted_override = overrides.get((day_date, block.id)) if override and getattr(override, "status", None) == "accepted" else None
                pending_override = override if override and getattr(override, "status", None) == "pending" else None

                analyst = None
                if accepted_override:
                    analyst = {
                        "id": accepted_override.override_analyst.id,
                        "name": accepted_override.override_analyst.get_full_name() or accepted_override.override_analyst.username,
                        "username": accepted_override.override_analyst.username,
                    }
                elif slot and slot.analyst:
                    analyst = {
                        "id": slot.analyst.id,
                        "name": slot.analyst.get_full_name() or slot.analyst.username,
                        "username": slot.analyst.username,
                    }

                result.append({
                    "date": day_date.isoformat(),
                    "day_of_week": dow,
                    "shift_block_id": block.id,
                    "shift_block_label": block.label,
                    "analyst": analyst,
                    "has_pending_override": pending_override is not None,
                    "override_id": override.id if override else None,
                })

        return Response(result)


class OnCallScheduleMonthView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)

        month_param = request.query_params.get("month")
        if not month_param:
            now = tz.now()
            month_param = f"{now.year}-{now.month:02d}"

        try:
            year_str, month_str = month_param.split("-")
            year = int(year_str)
            month = int(month_str)
        except (ValueError, AttributeError):
            return Response({"detail": "Invalid month format. Use YYYY-MM."}, status=400)

        import calendar
        import datetime as dt

        _, num_days = calendar.monthrange(year, month)
        dates = [dt.date(year, month, d) for d in range(1, num_days + 1)]

        blocks = list(ShiftBlock.objects.all().order_by("order"))
        slots = {
            (s.day_of_week, s.shift_block_id): s
            for s in RotationTemplateSlot.objects.select_related("analyst").all()
        }

        try:
            from oncall.models import ShiftOverride
            overrides = {
                (o.date, o.shift_block_id): o
                for o in ShiftOverride.objects.filter(
                    date__in=dates,
                    status="accepted",
                ).select_related("override_analyst")
            }
        except Exception:
            overrides = {}

        result = []
        for day_date in dates:
            dow = day_date.weekday()
            day_slots = []
            for block in blocks:
                override = overrides.get((day_date, block.id))
                slot = slots.get((dow, block.id))
                analyst = None
                if override:
                    analyst = {
                        "id": override.override_analyst.id,
                        "name": override.override_analyst.get_full_name() or override.override_analyst.username,
                        "initials": _initials(override.override_analyst),
                    }
                elif slot and slot.analyst:
                    analyst = {
                        "id": slot.analyst.id,
                        "name": slot.analyst.get_full_name() or slot.analyst.username,
                        "initials": _initials(slot.analyst),
                    }
                day_slots.append({
                    "shift_block_id": block.id,
                    "shift_block_label": block.label,
                    "analyst": analyst,
                })
            has_gap = any(s["analyst"] is None for s in day_slots)
            result.append({
                "date": day_date.isoformat(),
                "day_of_week": dow,
                "slots": day_slots,
                "has_gap": has_gap,
            })

        return Response(result)


def _initials(user):
    full = user.get_full_name()
    if full:
        parts = full.split()
        return "".join(p[0].upper() for p in parts[:2])
    return user.username[:2].upper()
