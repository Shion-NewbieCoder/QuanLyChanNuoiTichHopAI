from datetime import date, timedelta
from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.ai.providers import AIResponse
from apps.herds.models import Animal, AnimalGroup, Herd
from apps.vaccinations.models import VaccineSchedule
from .resources import RESOURCES


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith("/"):
                self.links.append(href)


class ManagementUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for key, role in (("manager", "quản lý"), ("technician", "kỹ thuật viên"), ("employee", "nhân viên"), ("none", None)):
            user = get_user_model().objects.create_user(username="ui-" + key)
            if role:
                user.groups.add(Group.objects.get(name=role))
            cls.users[key] = user
        cls.herd = Herd.objects.create(code="A01", name="Đàn bò", animal_type="bò", management_mode="group", quantity=12, status="active")
        cls.other = Herd.objects.create(code="Z02", name="Đàn dê", animal_type="dê", management_mode="individual", quantity=3, status="inactive")
        cls.animal = Animal.objects.create(code="CT01", herd=cls.herd, status="active")
        cls.group = AnimalGroup.objects.create(code="N01", name="Nhóm A", herd=cls.herd, quantity=3, status="active")
        cls.schedule = VaccineSchedule.objects.create(target=cls.herd, vaccine="Vaccine A", scheduled_date=date.today() - timedelta(days=1))
        cls.payloads = {
            "herds": dict(code="NEW", name="Đàn mới", animal_type="bò", management_mode="group", quantity=5, status="active"),
            "animals": dict(code="NEW", herd=cls.herd.pk, status="active"),
            "animal-groups": dict(code="NEW", name="Nhóm mới", herd=cls.herd.pk, quantity=4, status="active"),
            "pens": dict(code="NEW", name="Chuồng mới", location="Khu A", description="", status="active", herd=cls.herd.pk, animal="", animal_group=""),
            "care": dict(herd=cls.herd.pk, recorded_at="2026-09-08T08:15:00", activity="Vệ sinh", notes="Ghi nhận"),
            "care-schedules": dict(herd=cls.herd.pk, activity="Vệ sinh chuồng", scheduled_date="2026-10-01", status="scheduled"),
            "feed": dict(herd=cls.herd.pk, recorded_at="2026-09-08T08:15:00", feed_type="Cỏ", quantity="12.50", notes="Ghi nhận"),
            "medicine": dict(herd=cls.herd.pk, recorded_at="2026-09-08T08:15:00", medicine="Vitamin", dose="1.25", notes="Ghi nhận"),
            "vaccines": dict(target=cls.herd.pk, vaccine="Vaccine mới", scheduled_date="2026-10-01", status="scheduled"),
            "vaccination-records": dict(schedule=cls.schedule.pk, actual_date="2026-09-08", notes="Ghi nhận"),
            "growth": dict(target=cls.herd.pk, measurement_date="2026-09-08", weight="120.50", notes="Ghi nhận"),
            "reproduction": dict(target=cls.herd.pk, event_date="2026-09-08", event_type="Sự kiện ghi nhận", result="Ổn định", notes="Ghi nhận"),
            "sales": dict(target=cls.herd.pk, sale_date="2026-09-08", amount="125.00", quantity="", weight="", notes="Ghi nhận"),
        }

    def setUp(self):
        self.client.force_login(self.users["manager"])

    def create_record(self, slug):
        response = self.client.post(f"/{slug}/create/", self.payloads[slug])
        self.assertEqual(response.status_code, 302, response.content.decode())
        return RESOURCES[slug].model.objects.get(pk=int(response.url.strip("/").split("/")[-1]))

    def test_login_required_for_every_primary_route(self):
        self.client.logout()
        for path in [r.url for r in RESOURCES.values()] + ["/dashboard/", "/statistics/", "/ai/"]:
            with self.subTest(path=path):
                self.assertRedirects(self.client.get(path), "/login/?next=" + path)

    def test_manager_crud_for_every_resource(self):
        for slug, resource in RESOURCES.items():
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(resource.url).status_code, 200)
                self.assertContains(self.client.get(resource.url + "create/"), 'name="csrfmiddlewaretoken"')
                obj = self.create_record(slug)
                detail = f"{resource.url}{obj.pk}/"
                self.assertEqual(self.client.get(detail).status_code, 200)
                self.assertEqual(self.client.get(detail + "edit/").status_code, 200)
                payload = self.payloads[slug].copy()
                field = "code" if "code" in payload else "vaccine" if "vaccine" in payload else "notes" if "notes" in payload else "activity"
                payload[field] = "Đã chỉnh sửa"
                self.assertRedirects(self.client.post(detail + "edit/", payload), detail)
                obj.refresh_from_db()
                self.assertEqual(getattr(obj, field), "Đã chỉnh sửa")
                self.assertContains(self.client.get(detail + "delete/"), "Xác nhận xóa")
                self.assertTrue(resource.model.objects.filter(pk=obj.pk).exists())
                self.assertRedirects(self.client.post(detail + "delete/"), resource.url)
                self.assertFalse(resource.model.objects.filter(pk=obj.pk).exists())

    def test_role_matrix_enforced_on_screens_and_posts(self):
        records = {slug: self.create_record(slug) for slug in RESOURCES}
        technician_writes = {"care", "care-schedules", "feed", "medicine", "vaccines", "vaccination-records", "growth", "reproduction"}
        employee_creates = {"care", "care-schedules", "feed", "medicine"}
        for role in ("technician", "employee", "none"):
            self.client.force_login(self.users[role])
            for slug, resource in RESOURCES.items():
                with self.subTest(role=role, slug=slug):
                    readable = role != "none"
                    creatable = slug in (technician_writes if role == "technician" else employee_creates if role == "employee" else set())
                    editable = role == "technician" and slug in technician_writes
                    base = f"{resource.url}{records[slug].pk}/"
                    self.assertEqual(self.client.get(resource.url).status_code, 200 if readable else 403)
                    self.assertEqual(self.client.get(base).status_code, 200 if readable else 403)
                    for suffix, permitted, payload in (("create/", creatable, {}), (f"{records[slug].pk}/edit/", editable, {}), (f"{records[slug].pk}/delete/", False, {})):
                        self.assertEqual(self.client.get(resource.url + suffix).status_code, 200 if permitted else 403)
                        self.assertEqual(self.client.post(resource.url + suffix, payload).status_code, 200 if permitted else 403)
                    if readable:
                        page = self.client.get(base)
                        if not editable:
                            self.assertNotContains(page, base + "edit/")
                        self.assertNotContains(page, base + "delete/")

    def test_employee_care_creation_and_technician_update_work(self):
        self.client.force_login(self.users["employee"])
        for slug in ("care", "feed", "medicine"):
            obj = self.create_record(slug)
            self.client.force_login(self.users["technician"])
            payload = {**self.payloads[slug], "notes": "Kỹ thuật viên đã kiểm tra"}
            self.assertEqual(self.client.post(f"/{slug}/{obj.pk}/edit/", payload).status_code, 302)
            obj.refresh_from_db()
            self.assertEqual(obj.notes, payload["notes"])
            self.client.force_login(self.users["employee"])

    def test_care_schedule_screen_shows_alert_and_distinct_navigation(self):
        response = self.client.get("/care-schedules/")
        self.assertContains(response, "Lịch chăm sóc")
        self.assertContains(response, "Nhật ký chăm sóc")
        self.assertContains(response, "Chưa có dữ liệu")
        obj = self.create_record("care-schedules")
        self.assertContains(self.client.get(f"/care-schedules/{obj.pk}/"), "Cảnh báo")
        self.assertContains(self.client.get("/care-schedules/"), "Quá hạn")
        self.client.force_login(self.users["employee"])
        self.assertEqual(self.client.post(f"/care-schedules/{obj.pk}/edit/", self.payloads["care-schedules"]).status_code, 403)
        self.assertEqual(self.client.post(f"/care-schedules/{obj.pk}/delete/").status_code, 403)

    def test_invalid_forms_retain_values_and_do_not_write(self):
        for slug in RESOURCES:
            with self.subTest(slug=slug):
                count = RESOURCES[slug].model.objects.count()
                response = self.client.post(f"/{slug}/create/", {"notes": "Giữ lại nội dung"})
                self.assertContains(response, "Chưa thể lưu")
                self.assertEqual(RESOURCES[slug].model.objects.count(), count)
        response = self.client.post("/herds/create/", {**self.payloads["herds"], "quantity": -1})
        self.assertContains(response, 'value="NEW"')
        self.assertTrue(response.context["form"].errors["quantity"])

    def test_pen_xor_and_switch_target_flow(self):
        for extra in ({"herd": ""}, {"animal": self.animal.pk}, {"animal_group": self.group.pk}):
            response = self.client.post("/pens/create/", {**self.payloads["pens"], **extra})
            self.assertContains(response, "exactly one target")
        pen = self.create_record("pens")
        response = self.client.post(f"/pens/{pen.pk}/edit/", {**self.payloads["pens"], "herd": "", "animal": self.animal.pk})
        self.assertEqual(response.status_code, 302)
        pen.refresh_from_db()
        self.assertIsNone(pen.herd_id)
        self.assertEqual(pen.animal_id, self.animal.pk)

    def test_protected_delete_shows_safe_explanation(self):
        response = self.client.post(f"/herds/{self.herd.pk}/delete/")
        self.assertContains(response, "đang được dữ liệu khác tham chiếu")
        self.assertTrue(Herd.objects.filter(pk=self.herd.pk).exists())

    def test_search_filter_order_and_empty_state(self):
        cases = [({"search": "Đàn bò"}, [self.herd.pk]), ({"status": "inactive"}, [self.other.pk]),
                 ({"animal_type": "bò", "management_mode": "group"}, [self.herd.pk]),
                 ({"ordering": "quantity"}, [self.other.pk, self.herd.pk]),
                 ({"ordering": "-quantity"}, [self.herd.pk, self.other.pk])]
        for params, ids in cases:
            response = self.client.get("/herds/", params)
            self.assertEqual([row["pk"] for row in response.context["rows"]], ids)
        response = self.client.get("/herds/", {"search": "không-tồn-tại"})
        self.assertContains(response, "Chưa có dữ liệu đàn vật nuôi.")
        self.assertContains(response, "Thêm bản ghi đầu tiên")

    def test_all_resources_reuse_api_query_contract(self):
        for slug, resource in RESOURCES.items():
            with self.subTest(slug=slug):
                self.create_record(slug)
                view = resource.viewset
                field = view.ordering_fields[0]
                response = self.client.get(resource.url, {"ordering": "-" + field, "search": ""})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["pk"] for row in response.context["rows"]], list(resource.model.objects.order_by("-" + field).values_list("pk", flat=True)))
                filter_name = view.exact_filter_fields[0]
                filter_field = resource.model._meta.get_field(filter_name)
                expected = resource.model.objects.first()
                value = getattr(expected, filter_field.attname)
                if value is not None:
                    filtered = self.client.get(resource.url, {filter_name: value})
                    self.assertEqual({row["pk"] for row in filtered.context["rows"]}, set(resource.model.objects.filter(**{filter_name: value}).values_list("pk", flat=True)))

    def test_invalid_filter_is_safe(self):
        self.assertContains(self.client.get("/care/", {"herd": "bad"}), "Bộ lọc không hợp lệ", status_code=400)

    def test_pagination_keeps_query(self):
        Herd.objects.bulk_create([Herd(code=f"P{i:02}", name="Paged", animal_type="bò", management_mode="group", quantity=1, status="active") for i in range(25)])
        response = self.client.get("/herds/", {"search": "Paged", "ordering": "code", "page": 2})
        self.assertEqual(len(response.context["rows"]), 5)
        self.assertContains(response, "search=Paged&amp;ordering=code")

    def test_vaccine_persisted_and_derived_states_are_separate(self):
        response = self.client.get("/vaccines/")
        self.assertContains(response, "scheduled")
        self.assertContains(response, "Quá hạn")
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, "scheduled")

    def test_primary_navigation_links_resolve_for_each_role(self):
        for role in ("manager", "technician", "employee"):
            self.client.force_login(self.users[role])
            response = self.client.get("/herds/")
            parser = LinkParser(); parser.feed(response.content.decode())
            for href in set(parser.links):
                with self.subTest(role=role, href=href):
                    self.assertEqual(self.client.get(href).status_code, 200)
            if role == "employee":
                self.assertNotContains(response, 'href="/statistics/"')
                self.assertNotContains(response, 'href="/ai/"')

    def test_no_role_statistics_and_ai_restrictions(self):
        for role in self.users:
            self.client.force_login(self.users[role])
            for path in ("/statistics/", "/ai/"):
                self.assertEqual(self.client.get(path).status_code, 200 if role in ("manager", "technician") else 403)
            if role in ("employee", "none"):
                self.assertEqual(self.client.post("/ai/", {"feature": "reminders"}).status_code, 403)

    def test_csrf_required_and_valid_token_accepted(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.users["manager"])
        for slug in RESOURCES:
            self.assertEqual(client.post(f"/{slug}/create/", self.payloads[slug]).status_code, 403)
        for path in (f"/herds/{self.herd.pk}/edit/", f"/herds/{self.herd.pk}/delete/", "/ai/", "/logout/"):
            self.assertEqual(client.post(path, {}).status_code, 403)
        client.get("/herds/create/")
        response = client.post("/herds/create/", {**self.payloads["herds"], "csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assertEqual(response.status_code, 302)

    def test_html_and_bound_values_are_escaped(self):
        payload = '<script>alert("unsafe")</script>'
        self.herd.name = payload; self.herd.save()
        for path in ("/herds/", f"/herds/{self.herd.pk}/", f"/herds/{self.herd.pk}/edit/", "/ai/"):
            response = self.client.get(path)
            self.assertNotContains(response, payload)
            self.assertContains(response, "&lt;script&gt;")
        response = self.client.post("/herds/create/", {**self.payloads["herds"], "name": payload, "quantity": -1})
        self.assertNotContains(response, payload)
        self.assertContains(response, "&lt;script&gt;")

    @override_settings(DEBUG=True)
    def test_safe_404_and_database_error_even_in_demo_debug(self):
        missing = self.client.get("/not-a-page/")
        self.assertContains(missing, "Không tìm thấy", status_code=404)
        self.assertEqual(missing["X-Frame-Options"], "DENY")
        self.assertContains(self.client.get("/herds/999999/"), "Không tìm thấy", status_code=404)
        with patch("apps.dashboard.forms.ResourceForm.save", side_effect=DatabaseError("SECRET DATABASE PATH")):
            response = self.client.post("/herds/create/", self.payloads["herds"])
        self.assertContains(response, "Chưa thể xử lý", status_code=500)
        self.assertNotContains(response, "SECRET DATABASE PATH", status_code=500)

    def test_ai_unconfigured_provider_is_friendly(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "", "AI_API_KEY": ""}):
            response = self.client.post("/ai/", {"feature": "herd_summary", "herd_summary-herd_id": self.herd.pk})
        self.assertContains(response, "AI chưa được cấu hình hoặc cấu hình không hợp lệ.")
        self.assertNotContains(response, "Traceback")

    def test_ai_validation_and_insufficient_data(self):
        invalid = self.client.post("/ai/", {"feature": "reminders", "reminders-scope": "herd"})
        self.assertTrue(invalid.context["ai_cards"][0]["form"].errors)
        response = self.client.post("/ai/", {"feature": "growth_report", "growth_report-herd_id": self.herd.pk})
        self.assertContains(response, "Chưa có đủ dữ liệu")
        self.assertContains(response, "không thay thế bác sĩ thú y")

    def test_ai_generated_text_is_escaped(self):
        class Provider:
            name = "fake"
            def generate(self, request):
                return AIResponse(text='<script>alert("ai")</script>', provider=self.name)
        with patch("apps.ai.herd_summary.get_configured_provider", return_value=Provider()):
            response = self.client.post("/ai/", {"feature": "herd_summary", "herd_summary-herd_id": self.herd.pk})
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("ai")</script>')

    def test_ai_assistant_renders_chat_form_with_session_csrf_and_existing_features(self):
        response = self.client.get("/ai/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-ai-chat')
        self.assertContains(response, 'data-chat-history')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'name="question"')
        self.assertContains(response, "ai-chat.js")
        for title in ("Nhắc lịch", "Tóm tắt đàn", "Báo cáo tăng trưởng"):
            self.assertContains(response, title)

    def test_login_ui_preserves_next_and_safe_logout(self):
        self.client.logout()
        response = self.client.get("/login/?next=/herds/")
        self.assertContains(response, 'name="next" value="/herds/"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.client.force_login(self.users["manager"])
        self.assertEqual(self.client.get("/logout/").status_code, 405)

    def test_post_to_read_screens_never_deletes(self):
        self.assertEqual(self.client.post(f"/herds/{self.herd.pk}/").status_code, 405)
        self.assertTrue(Herd.objects.filter(pk=self.herd.pk).exists())
