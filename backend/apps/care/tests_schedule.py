from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.herds.models import Herd

from .models import CareSchedule
from .serializers import CareScheduleSerializer, get_care_alert_classification


class CareScheduleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.herd = Herd.objects.create(code="CARE-A", name="Đàn A", animal_type="bò", management_mode="group", quantity=4, status="active")
        cls.other = Herd.objects.create(code="CARE-B", name="Đàn B", animal_type="bò", management_mode="group", quantity=3, status="active")
        cls.users = {}
        for role in ("quản lý", "kỹ thuật viên", "nhân viên", None):
            user = get_user_model().objects.create_user(username=f"schedule-{role}")
            if role:
                user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user

    def test_model_and_serializer_validation_preserve_past_date(self):
        past = date.today() - timedelta(days=1)
        schedule = CareSchedule(herd=self.herd, activity="  Vệ sinh  ", scheduled_date=past)
        schedule.full_clean()
        self.assertEqual(schedule.activity, "Vệ sinh")
        schedule.save()
        self.assertEqual(CareSchedule.objects.get(pk=schedule.pk).status, "scheduled")
        for changes in ({"activity": "  "}, {"herd_id": 999999}, {"scheduled_date": None}, {"status": "unknown"}):
            bad = CareSchedule(herd=self.herd, activity="Vệ sinh", scheduled_date=past)
            for name, value in changes.items():
                setattr(bad, name, value)
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                bad.full_clean()
        for payload in (
            {"herd": self.herd.pk, "activity": "  ", "scheduled_date": past.isoformat()},
            {"herd": 999999, "activity": "Vệ sinh", "scheduled_date": past.isoformat()},
            {"herd": self.herd.pk, "activity": "Vệ sinh", "scheduled_date": "bad"},
            {"herd": self.herd.pk, "activity": "Vệ sinh", "scheduled_date": past.isoformat(), "status": "unknown"},
        ):
            with self.subTest(payload=payload):
                self.assertFalse(CareScheduleSerializer(data=payload).is_valid())

    def test_direct_orm_save_validates_and_trims_activity(self):
        past = date.today() - timedelta(days=1)
        for values in ({"activity": "   "}, {"activity": "Vệ sinh", "status": "unknown"}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                CareSchedule.objects.create(herd=self.herd, scheduled_date=past, **values)
            self.assertEqual(CareSchedule.objects.count(), 0)

        schedule = CareSchedule.objects.create(
            herd=self.herd, activity="  Vệ sinh chuồng  ", scheduled_date=past,
        )
        schedule.refresh_from_db()
        self.assertEqual(schedule.activity, "Vệ sinh chuồng")
        self.assertEqual(schedule.scheduled_date, past)
        self.assertEqual(CareSchedule.objects.count(), 1)

    def test_alert_boundaries_do_not_change_status(self):
        today = date(2026, 10, 26)
        schedule = CareSchedule.objects.create(herd=self.herd, activity="Việc A", scheduled_date=today)
        for offset, expected in ((-1, "overdue"), (0, "due today"), (7, "due soon"), (8, "scheduled-not-yet-due")):
            schedule.scheduled_date = today + timedelta(days=offset)
            self.assertEqual(get_care_alert_classification(schedule, today), expected)
        for status in ("completed", "cancelled"):
            schedule.status = status
            self.assertIsNone(get_care_alert_classification(schedule, today))
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, "scheduled")
        self.assertEqual(schedule.scheduled_date, today)

    def test_api_crud_search_filters_order_and_readonly_alert(self):
        self.client.force_login(self.users["quản lý"])
        url = reverse("careschedule-list")
        first = self.client.post(url, {"herd": self.herd.pk, "activity": "  Vệ sinh  ", "scheduled_date": "2026-10-01", "alert_classification": "fake"}, content_type="application/json")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json()["activity"], "Vệ sinh")
        self.assertNotEqual(first.json()["alert_classification"], "fake")
        second = self.client.post(url, {"herd": self.other.pk, "activity": "Cho ăn", "scheduled_date": "2026-11-01", "status": "due"}, content_type="application/json")
        self.assertEqual(second.status_code, 201)
        first_id = first.json()["id"]
        for params, expected in (({"search": "Vệ sinh"}, [first_id]), ({"herd": self.herd.pk}, [first_id]), ({"status": "due"}, [second.json()["id"]]), ({"ordering": "-scheduled_date"}, [second.json()["id"], first_id])):
            with self.subTest(params=params):
                self.assertEqual([row["id"] for row in self.client.get(url, params).json()], expected)
        detail = reverse("careschedule-detail", args=[first_id])
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.patch(detail, {"status": "completed"}, content_type="application/json").status_code, 200)
        self.assertIsNone(self.client.get(detail).json()["alert_classification"])
        self.assertEqual(self.client.delete(detail).status_code, 204)

    def test_api_role_matrix(self):
        obj = CareSchedule.objects.create(herd=self.herd, activity="Việc A", scheduled_date=date.today())
        url = reverse("careschedule-list")
        detail = reverse("careschedule-detail", args=[obj.pk])
        payload = {"herd": self.herd.pk, "activity": "Việc B", "scheduled_date": "2026-10-26"}
        for role, can_create, can_update, can_delete in (("quản lý", True, True, True), ("kỹ thuật viên", True, True, False), ("nhân viên", True, False, False), (None, False, False, False)):
            with self.subTest(role=role):
                self.client.force_login(self.users[role])
                self.assertEqual(self.client.get(url).status_code, 200 if role else 403)
                self.assertEqual(self.client.get(detail).status_code, 200 if role else 403)
                self.assertEqual(self.client.post(url, payload, content_type="application/json").status_code, 201 if can_create else 403)
                self.assertEqual(self.client.patch(detail, {"activity": "Updated"}, content_type="application/json").status_code, 200 if can_update else 403)
                if not can_delete:
                    self.assertEqual(self.client.delete(detail).status_code, 403)
        self.client.logout()
        self.assertIn(self.client.get(url).status_code, (401, 403))
