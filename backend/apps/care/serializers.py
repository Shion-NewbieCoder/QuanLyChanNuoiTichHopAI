from decimal import Decimal
from datetime import date

from rest_framework import serializers

from apps.domain_validation import validate_care_log

from .models import CareLog, CareSchedule, FeedRecord, MedicineRecord


def get_care_alert_classification(schedule, today=None):
    if schedule.status in {CareSchedule.Status.COMPLETED, CareSchedule.Status.CANCELLED}:
        return None
    delta = (schedule.scheduled_date - (today or date.today())).days
    if delta < 0:
        return "overdue"
    if delta == 0:
        return "due today"
    if delta <= 7:
        return "due soon"
    return "scheduled-not-yet-due"


class CareScheduleSerializer(serializers.ModelSerializer):
    alert_classification = serializers.SerializerMethodField()

    class Meta:
        model = CareSchedule
        fields = ["id", "herd", "activity", "scheduled_date", "status", "alert_classification"]

    def get_alert_classification(self, obj):
        return get_care_alert_classification(obj)

    def validate_activity(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("activity is required.")
        return value

    def validate(self, attrs):
        instance = self.instance or CareSchedule()
        for name, value in attrs.items():
            setattr(instance, name, value)
        instance.full_clean()
        return attrs


class CareLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareLog
        fields = ["id", "herd", "recorded_at", "activity", "notes"]

    def validate(self, attrs):
        instance = self.instance or CareLog()
        for field_name in ["herd", "recorded_at", "activity", "notes"]:
            if field_name in attrs:
                setattr(instance, field_name, attrs[field_name])
        validate_care_log(instance)
        return attrs


class FeedRecordSerializer(serializers.ModelSerializer):
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))

    class Meta:
        model = FeedRecord
        fields = ["id", "herd", "recorded_at", "feed_type", "quantity", "notes"]


class MedicineRecordSerializer(serializers.ModelSerializer):
    dose = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))

    class Meta:
        model = MedicineRecord
        fields = ["id", "herd", "recorded_at", "medicine", "dose", "notes"]
