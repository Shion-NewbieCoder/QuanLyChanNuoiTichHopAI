from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from apps.growth.models import GrowthRecord
from apps.herds.models import Herd
from apps.sales.models import SaleRecord
from apps.statistics.models import CostRecord, HerdLossRecord
from apps.users.roles import ROLE_EMPLOYEE, ROLE_MANAGEMENT, ROLE_TECHNICIAN
from apps.vaccinations.models import VaccineSchedule


class DashboardViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in (ROLE_MANAGEMENT, ROLE_TECHNICIAN, ROLE_EMPLOYEE):
            user = get_user_model().objects.create_user(username=f"dashboard-{role}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.no_role = get_user_model().objects.create_user(username="dashboard-no-role")
        cls.herd = Herd.objects.create(
            code="DASH-001",
            name='<script>alert("unsafe")</script>',
            animal_type="cattle",
            management_mode="group",
            quantity=20,
            status="active",
        )
        VaccineSchedule.objects.create(
            target=cls.herd,
            vaccine="Vaccine dashboard",
            scheduled_date=date.today() + timedelta(days=2),
        )
        GrowthRecord.objects.create(
            target=cls.herd,
            measurement_date=date(2026, 1, 1),
            weight=Decimal("100.00"),
        )
        SaleRecord.objects.create(
            target=cls.herd,
            sale_date=date(2026, 1, 2),
            amount=Decimal("750.00"),
        )
        CostRecord.objects.create(
            herd=cls.herd,
            cost_date=date(2026, 1, 3),
            category=CostRecord.Category.FEED,
            amount=Decimal("125.00"),
        )
        HerdLossRecord.objects.create(
            herd=cls.herd,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            opening_quantity=20,
            lost_quantity=2,
        )

    def get_dashboard(self, user):
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.client.logout()
        return response

    def test_unauthenticated_user_is_redirected_to_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('dashboard')}",
        )

    def test_recognized_roles_can_access_and_no_role_is_denied(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                response = self.get_dashboard(user)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "dashboard/dashboard.html")
        self.assertEqual(self.get_dashboard(self.no_role).status_code, 403)

    def test_manager_dashboard_renders_navigation_cards_and_service_data(self):
        response = self.get_dashboard(self.users[ROLE_MANAGEMENT])
        for label in (
            "Tổng quan",
            "Đàn",
            "Chuồng",
            "Nhật ký chăm sóc",
            "Lịch chăm sóc",
            "Vaccine",
            "Tăng trưởng",
            "Sinh sản",
            "Xuất bán",
            "Thống kê",
            "AI Assistant",
        ):
            self.assertContains(response, label)
        self.assertContains(response, "DASH-001")
        self.assertContains(response, "Vaccine dashboard")
        self.assertContains(response, "750.00")
        self.assertContains(response, "125.00")
        self.assertContains(response, "10.00%")

    def test_statistics_are_obtained_from_existing_services(self):
        with (
            patch(
                "apps.dashboard.views.get_growth_statistics",
                return_value={
                    "record_count": 7,
                    "total_weight": "700.00",
                    "average_weight": "321.00",
                },
            ) as growth_service,
            patch(
                "apps.dashboard.views.get_cost_statistics",
                return_value={"total_cost": "654.00", "by_category": {}},
            ) as cost_service,
            patch(
                "apps.dashboard.views.get_loss_statistics",
                return_value={
                    "record_count": 1,
                    "opening_quantity": 10,
                    "lost_quantity": 1,
                    "loss_rate_percent": "10.00",
                },
            ) as loss_service,
        ):
            response = self.get_dashboard(self.users[ROLE_TECHNICIAN])
        self.assertContains(response, "321.00")
        self.assertContains(response, "654.00")
        growth_service.assert_called_once_with()
        cost_service.assert_called_once_with()
        loss_service.assert_called_once_with()

    def test_employee_sees_readable_business_sections_but_not_statistics_or_ai_controls(self):
        response = self.get_dashboard(self.users[ROLE_EMPLOYEE])
        self.assertContains(response, "Vaccine dashboard")
        self.assertContains(response, "Tăng trưởng gần đây")
        self.assertNotContains(response, 'id="statistics"')
        self.assertNotContains(response, 'id="ai-assistant"')
        self.assertNotContains(response, reverse("ai-reminders"))
        self.client.force_login(self.users[ROLE_EMPLOYEE])
        api_response = self.client.post(
            reverse("ai-reminders"),
            {"scope": "all"},
            content_type="application/json",
        )
        self.assertEqual(api_response.status_code, 403)

    def test_ai_forms_are_role_aware_labeled_and_csrf_protected(self):
        for role in (ROLE_MANAGEMENT, ROLE_TECHNICIAN):
            response = self.get_dashboard(self.users[role])
            with self.subTest(role=role):
                self.assertContains(response, reverse("ai-reminders"))
                self.assertContains(response, reverse("ai-herd-summary"))
                self.assertContains(response, reverse("ai-growth-report"))
                self.assertContains(response, "csrfmiddlewaretoken", count=4)
                self.assertContains(response, "Gợi ý từ AI")
                self.assertContains(response, "Chọn đàn", count=2)

    def test_user_controlled_content_is_autoescaped(self):
        response = self.get_dashboard(self.users[ROLE_MANAGEMENT])
        self.assertNotContains(response, '<script>alert("unsafe")</script>')
        self.assertContains(response, "&lt;script&gt;alert(&quot;unsafe&quot;)&lt;/script&gt;")

    def test_database_failure_renders_safe_error_state(self):
        self.client.force_login(self.users[ROLE_MANAGEMENT])
        with patch(
            "apps.dashboard.views.build_dashboard_context",
            side_effect=DatabaseError("internal database detail"),
        ):
            response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Không thể tải dữ liệu tổng quan. Vui lòng thử lại.",
        )
        self.assertNotContains(response, "internal database detail")


class EmptyDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_user(username="empty-dashboard")
        cls.manager.groups.add(Group.objects.get(name=ROLE_MANAGEMENT))

    def test_empty_database_renders_empty_states_without_template_error(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Không có lịch vaccine cần chú ý.")
        self.assertContains(response, "Chưa có dữ liệu tăng trưởng.")
        self.assertContains(response, "Chưa có đàn", count=2)
