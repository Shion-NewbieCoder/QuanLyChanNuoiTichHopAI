import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("care", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="CareSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activity", models.CharField(max_length=200)),
                ("scheduled_date", models.DateField()),
                ("status", models.CharField(choices=[("scheduled", "Đã lập lịch"), ("due", "Đến hạn / cần chú ý"), ("completed", "Đã thực hiện"), ("cancelled", "Đã hủy")], default="scheduled", max_length=40)),
                ("herd", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="care_schedules", to="herds.herd")),
            ],
            options={"ordering": ["scheduled_date", "activity"]},
        ),
    ]
