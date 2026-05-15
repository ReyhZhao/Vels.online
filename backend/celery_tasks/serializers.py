import datetime

from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult
from rest_framework import serializers


class TaskResultListSerializer(serializers.ModelSerializer):
    duration = serializers.SerializerMethodField()

    class Meta:
        model = TaskResult
        fields = [
            "task_id",
            "task_name",
            "status",
            "date_created",
            "date_done",
            "duration",
            "worker",
        ]

    def get_duration(self, obj):
        if obj.date_done and obj.date_created:
            return round((obj.date_done - obj.date_created).total_seconds(), 1)
        return None


class TaskResultDetailSerializer(TaskResultListSerializer):
    class Meta(TaskResultListSerializer.Meta):
        fields = TaskResultListSerializer.Meta.fields + ["result", "traceback"]


class PeriodicTaskSerializer(serializers.ModelSerializer):
    schedule_display = serializers.SerializerMethodField()
    next_run = serializers.SerializerMethodField()

    class Meta:
        model = PeriodicTask
        fields = [
            "id",
            "name",
            "task",
            "enabled",
            "last_run_at",
            "next_run",
            "schedule_display",
            "total_run_count",
        ]

    def get_schedule_display(self, obj):
        if obj.interval:
            return str(obj.interval)
        if obj.crontab:
            ct = obj.crontab
            return f"{ct.minute} {ct.hour} {ct.day_of_month} {ct.month_of_year} {ct.day_of_week}"
        return "unknown"

    def get_next_run(self, obj):
        try:
            if obj.interval:
                interval = obj.interval
                period = interval.period
                every = interval.every
                seconds_map = {
                    "seconds": 1,
                    "minutes": 60,
                    "hours": 3600,
                    "days": 86400,
                }
                seconds = every * seconds_map.get(period, 1)
                base = obj.last_run_at or datetime.datetime.now(tz=datetime.timezone.utc)
                return (base + datetime.timedelta(seconds=seconds)).isoformat()
            if obj.crontab:
                from croniter import croniter
                ct = obj.crontab
                cron_str = f"{ct.minute} {ct.hour} {ct.day_of_month} {ct.month_of_year} {ct.day_of_week}"
                base = obj.last_run_at or datetime.datetime.now(tz=datetime.timezone.utc)
                return croniter(cron_str, base).get_next(datetime.datetime).isoformat()
        except Exception:
            pass
        return None


class PeriodicTaskToggleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PeriodicTask
        fields = ["enabled"]
