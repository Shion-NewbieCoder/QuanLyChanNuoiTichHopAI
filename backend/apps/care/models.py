from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.core.exceptions import ValidationError


class CareSchedule(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Đã lập lịch"
        DUE = "due", "Đến hạn / cần chú ý"
        COMPLETED = "completed", "Đã thực hiện"
        CANCELLED = "cancelled", "Đã hủy"

    herd = models.ForeignKey("herds.Herd", on_delete=models.PROTECT, related_name="care_schedules")
    activity = models.CharField(max_length=200)
    scheduled_date = models.DateField()
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        ordering = ["scheduled_date", "activity"]

    def clean(self):
        super().clean()
        if not self.activity or not self.activity.strip():
            raise ValidationError({"activity": "activity is required."})
        if self.activity:
            self.activity = self.activity.strip()
        if self.herd_id is None or not self._meta.get_field("herd").remote_field.model.objects.filter(pk=self.herd_id).exists():
            raise ValidationError({"herd": "CareSchedule requires a valid Herd target."})
        if self.scheduled_date is None:
            raise ValidationError({"scheduled_date": "scheduled_date is required."})
        if self.status not in self.Status.values:
            raise ValidationError({"status": "status must be a valid care schedule state."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class CareLog(models.Model):
    herd = models.ForeignKey(
        "herds.Herd",
        on_delete=models.PROTECT,
        related_name="care_logs",
    )
    recorded_at = models.DateTimeField()
    activity = models.CharField(max_length=200)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-recorded_at"]


class FeedRecord(models.Model):
    herd = models.ForeignKey(
        "herds.Herd",
        on_delete=models.PROTECT,
        related_name="feed_records",
    )
    recorded_at = models.DateTimeField()
    feed_type = models.CharField(max_length=200)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-recorded_at"]


class MedicineRecord(models.Model):
    herd = models.ForeignKey(
        "herds.Herd",
        on_delete=models.PROTECT,
        related_name="medicine_records",
    )
    recorded_at = models.DateTimeField()
    medicine = models.CharField(max_length=200)
    dose = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-recorded_at"]
