"""Presentation metadata; business contracts remain owned by API viewsets."""
from dataclasses import dataclass

from apps.care.views import CareLogViewSet, CareScheduleViewSet, FeedRecordViewSet, MedicineRecordViewSet
from apps.growth.views import GrowthRecordViewSet
from apps.herds.views import AnimalGroupViewSet, AnimalViewSet, HerdViewSet
from apps.pens.views import PenViewSet
from apps.reproduction.views import ReproductionRecordViewSet
from apps.sales.views import SaleRecordViewSet
from apps.vaccinations.views import VaccinationRecordViewSet, VaccineScheduleViewSet


LABELS = {
    "id": "Mã bản ghi", "code": "Mã", "name": "Tên", "animal_type": "Loại vật nuôi",
    "management_mode": "Phương thức quản lý", "quantity": "Số lượng", "status": "Trạng thái",
    "herd": "Đàn vật nuôi", "target": "Đàn vật nuôi", "animal_group": "Nhóm vật nuôi",
    "animal": "Cá thể", "location": "Vị trí", "description": "Mô tả",
    "recorded_at": "Thời điểm ghi nhận", "activity": "Hoạt động", "notes": "Ghi chú",
    "feed_type": "Loại thức ăn", "medicine": "Thuốc", "dose": "Liều lượng",
    "vaccine": "Vaccine", "scheduled_date": "Ngày dự kiến", "schedule": "Lịch vaccine",
    "actual_date": "Ngày thực hiện", "measurement_date": "Ngày đo", "weight": "Khối lượng",
    "event_date": "Ngày sự kiện", "event_type": "Sự kiện", "result": "Kết quả",
    "sale_date": "Ngày xuất bán", "amount": "Số tiền", "alert_classification": "Cảnh báo",
}
ALERT_LABELS = {
    "overdue": "Quá hạn", "due today": "Đến hạn hôm nay", "due soon": "Trong 7 ngày tới",
    "scheduled-not-yet-due": "Chưa đến hạn",
}


@dataclass(frozen=True)
class Resource:
    slug: str
    title: str
    viewset: type
    columns: tuple
    hint: str = ""

    @property
    def model(self):
        return self.viewset.queryset.model

    @property
    def fields(self):
        return [name for name, field in self.viewset.serializer_class().fields.items() if not field.read_only]

    @property
    def url(self):
        return f"/{self.slug}/"

    @property
    def section(self):
        return "vaccines" if self.slug == "vaccination-records" else self.slug


RESOURCES = {
    r.slug: r for r in (
        Resource("herds", "Đàn vật nuôi", HerdViewSet, ("code", "name", "animal_type", "management_mode", "quantity", "status")),
        Resource("animals", "Cá thể", AnimalViewSet, ("code", "herd", "status")),
        Resource("animal-groups", "Nhóm vật nuôi", AnimalGroupViewSet, ("code", "name", "herd", "quantity", "status")),
        Resource("pens", "Chuồng trại", PenViewSet, ("code", "name", "location", "herd", "animal_group", "animal", "status"),
                 "Chọn đúng một đối tượng: đàn, nhóm vật nuôi hoặc cá thể. Để trống hai lựa chọn còn lại."),
        Resource("care", "Nhật ký chăm sóc", CareLogViewSet, ("herd", "recorded_at", "activity", "notes"), "Nhật ký chăm sóc được ghi nhận cho đàn vật nuôi."),
        Resource("care-schedules", "Lịch chăm sóc", CareScheduleViewSet, ("herd", "activity", "scheduled_date", "status", "alert_classification"),
                 "Cảnh báo theo ngày được tính khi xem; trạng thái lịch đã lưu không tự thay đổi."),
        Resource("feed", "Thức ăn", FeedRecordViewSet, ("herd", "recorded_at", "feed_type", "quantity")),
        Resource("medicine", "Thuốc", MedicineRecordViewSet, ("herd", "recorded_at", "medicine", "dose")),
        Resource("vaccines", "Vaccine", VaccineScheduleViewSet, ("target", "vaccine", "scheduled_date", "status", "alert_classification"),
                 "Cảnh báo theo ngày được tính khi xem; không thay đổi trạng thái đã lưu của lịch vaccine."),
        Resource("vaccination-records", "Lần tiêm vaccine", VaccinationRecordViewSet, ("schedule", "actual_date", "notes")),
        Resource("growth", "Tăng trưởng", GrowthRecordViewSet, ("target", "measurement_date", "weight", "notes")),
        Resource("reproduction", "Sinh sản", ReproductionRecordViewSet, ("target", "event_date", "event_type", "result")),
        Resource("sales", "Xuất bán", SaleRecordViewSet, ("target", "sale_date", "quantity", "weight", "amount"),
                 "Doanh thu được tổng hợp từ số tiền xuất bán đã ghi nhận."),
    )
}
