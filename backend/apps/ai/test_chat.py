"""Offline tests for the scoped, read-only livestock chat endpoint."""

from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.care.models import CareLog
from apps.herds.models import Animal, AnimalGroup, Herd
from apps.growth.models import GrowthRecord
from apps.pens.models import Pen
from apps.sales.models import SaleRecord
from apps.statistics.models import CostRecord, HerdLossRecord
from apps.users.roles import ROLE_EMPLOYEE, ROLE_MANAGEMENT, ROLE_TECHNICIAN
from apps.vaccinations.models import VaccineSchedule

from .providers import AIConfigurationError, AIProviderError, AIResponse
from .openai_provider import normalize_request
from .chat import _has_unmatched_explicit_herd, _herd_matches, collect_chat_facts, select_chat_sources


class ChatEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for index, role in enumerate((ROLE_MANAGEMENT, ROLE_TECHNICIAN, ROLE_EMPLOYEE, None)):
            user = get_user_model().objects.create_user(username=f"chat-role-{index}")
            if role:
                user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.herd = Herd.objects.create(
            code="CHAT-001", name="Nông trại mẫu", animal_type="cattle",
            management_mode="group", quantity=14, status="active",
        )
        cls.animal = Animal.objects.create(code="AN-01", herd=cls.herd, status="active")
        cls.group = AnimalGroup.objects.create(
            code="GR-01", name="Nhóm thử", herd=cls.herd, quantity=4, status="active",
        )
        Pen.objects.create(code="PEN-01", name="Chuồng A", status="active", herd=cls.herd)
        CareLog.objects.create(
            herd=cls.herd, recorded_at="2026-06-01T08:00:00Z", activity="Vệ sinh chuồng", notes="Đã ghi nhận",
        )
        VaccineSchedule.objects.create(
            target=cls.herd, vaccine="Vaccine A", scheduled_date=date(2026, 6, 10), status="scheduled",
        )

    def setUp(self):
        self.client.force_login(self.users[ROLE_MANAGEMENT])

    def snapshot(self):
        ignored = {"auth", "users", "sessions", "contenttypes", "admin"}
        return {
            model._meta.label: list(model.objects.order_by("pk").values())
            for model in apps.get_models() if model._meta.app_label not in ignored
        }

    def post_chat(self, question, **extra):
        return self.client.post(
            "/api/ai/chat", {"question": question, **extra}, content_type="application/json",
        )

    @staticmethod
    def fake_provider(answer="Có 14 vật nuôi trong đàn CHAT-001.", error=None):
        provider = Mock(name="fake-provider")
        provider.name = "fake"
        if error:
            provider.generate.side_effect = error
        else:
            provider.generate.return_value = AIResponse(answer, "fake")
        return provider

    def test_in_scope_question_uses_only_selected_minimal_sources(self):
        provider = self.fake_provider()
        before = self.snapshot()
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat("Đàn vật nuôi nào đang được ghi nhận?")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Có 14 vật nuôi trong đàn CHAT-001.")
        request = provider.generate.call_args.args[0]
        self.assertEqual(request.prompt_version, "livestock-chat-v1")
        self.assertEqual(set(request.context["sources"]), {"herds"})
        self.assertEqual(request.context["sources"]["herds"], [{
            "code": "CHAT-001", "name": "Nông trại mẫu", "animal_type": "cattle",
            "management_mode": "group", "quantity": 14, "status": "active",
        }])
        self.assertNotIn("CareLog", str(request.context))
        self.assertNotIn("groups", str(request.context))
        self.assertEqual(self.snapshot(), before)

    def test_herd_count_question_is_answered_from_database_without_provider(self):
        Herd.objects.create(
            code="CHAT-002", name="Trang trại khác", animal_type="cattle",
            management_mode="group", quantity=8, status="active",
        )
        with patch("apps.ai.chat.get_configured_provider") as provider, \
                patch("apps.ai.chat.collect_chat_facts") as collect:
            response = self.post_chat("Hiện có bao nhiêu đàn")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Hệ thống hiện ghi nhận 2 đàn.")
        self.assertEqual(response.json()["source_count"], 2)
        collect.assert_not_called()
        provider.assert_not_called()

    def test_sample_herd_quantity_statistics_are_calculated_from_database(self):
        maximum = Herd.objects.create(
            code="CHAT-MAX", name="Đàn có số lượng lớn", animal_type="cattle",
            management_mode="group", quantity=125, status="inactive",
        )
        minimum = Herd.objects.create(
            code="CHAT-MIN", name="Đàn có số lượng nhỏ", animal_type="cattle",
            management_mode="individual", quantity=3, status="active",
        )
        questions = (
            ("Hiện có bao nhiêu đàn?", "Hệ thống hiện ghi nhận 3 đàn."),
            (
                "Đàn nào có số lượng vật nuôi nhiều nhất?",
                "Đàn có số lượng ghi nhận nhiều nhất: CHAT-MAX — Đàn có số lượng lớn (125 con).",
            ),
            (
                "Đàn nào có số lượng vật nuôi ít nhất?",
                "Đàn có số lượng ghi nhận ít nhất: CHAT-MIN — Đàn có số lượng nhỏ (3 con).",
            ),
            (
                "Đàn nào đông nhất và có bao nhiêu con?",
                "Đàn có số lượng ghi nhận nhiều nhất: CHAT-MAX — Đàn có số lượng lớn (125 con).",
            ),
            (
                "Đàn nào nhiều nhất?",
                "Đàn có số lượng ghi nhận nhiều nhất: CHAT-MAX — Đàn có số lượng lớn (125 con).",
            ),
            (
                "Đàn nào ít nhất?",
                "Đàn có số lượng ghi nhận ít nhất: CHAT-MIN — Đàn có số lượng nhỏ (3 con).",
            ),
            (
                "Đàn nào có nhiều con nhất?",
                "Đàn có số lượng ghi nhận nhiều nhất: CHAT-MAX — Đàn có số lượng lớn (125 con).",
            ),
            (
                "Đàn nào có ít con nhất?",
                "Đàn có số lượng ghi nhận ít nhất: CHAT-MIN — Đàn có số lượng nhỏ (3 con).",
            ),
        )
        fake_provider = self.fake_provider()
        for question, expected_answer in questions:
            with self.subTest(question=question), \
                    patch("apps.ai.chat.get_configured_provider", return_value=fake_provider) as provider, \
                    patch("apps.ai.chat.collect_chat_facts") as collect:
                response = self.post_chat(question)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["answer"], expected_answer)
            collect.assert_not_called()
            provider.assert_not_called()
        self.assertEqual(Herd.objects.count(), 3)
        self.assertEqual(Herd.objects.get(pk=maximum.pk).quantity, 125)
        self.assertEqual(Herd.objects.get(pk=minimum.pk).quantity, 3)

    def test_explicit_herd_quantity_question_uses_only_that_herds_database_value(self):
        demo_herd = Herd.objects.create(
            code="DEMO-HERD-001", name="Demo herd", animal_type="cattle",
            management_mode="group", quantity=73, status="active",
        )
        other_herd = Herd.objects.create(
            code="DEMO-HERD-002", name="Other herd", animal_type="cattle",
            management_mode="group", quantity=999, status="active",
        )
        fake_provider = self.fake_provider("wrong value")
        with patch("apps.ai.chat.get_configured_provider", return_value=fake_provider) as provider, \
                patch("apps.ai.chat.collect_chat_facts") as collect:
            response = self.post_chat("Đàn DEMO-HERD-001 hiện có bao nhiêu con?")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["answer"],
            "Đàn DEMO-HERD-001 (Demo herd) có 73 con theo số lượng đang ghi nhận trong hệ thống.",
        )
        self.assertEqual(response.json()["source_count"], 1)
        collect.assert_not_called()
        provider.assert_not_called()
        self.assertNotEqual(demo_herd.quantity, other_herd.quantity)

    def test_gold_price_question_is_rejected_before_herd_or_source_queries(self):
        fake_provider = self.fake_provider()
        with patch("apps.ai.chat._herd_matches") as match_herd, \
                patch("apps.ai.chat.collect_chat_facts") as collect, \
                patch("apps.ai.chat.get_configured_provider", return_value=fake_provider) as provider:
            response = self.post_chat("Giá vàng hôm nay bao nhiêu?")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ngoài phạm vi", response.json()["answer"])
        match_herd.assert_not_called()
        collect.assert_not_called()
        provider.assert_not_called()

    def test_tied_herd_quantity_extrema_are_reported_without_choosing_arbitrarily(self):
        first = Herd.objects.create(
            code="CHAT-MIN-A", name="Đàn nhỏ A", animal_type="cattle",
            management_mode="group", quantity=0, status="active",
        )
        second = Herd.objects.create(
            code="CHAT-MIN-B", name="Đàn nhỏ B", animal_type="cattle",
            management_mode="individual", quantity=0, status="inactive",
        )
        fake_provider = self.fake_provider()
        with patch("apps.ai.chat.get_configured_provider", return_value=fake_provider) as provider:
            response = self.post_chat("Đàn nào có số lượng vật nuôi ít nhất?")
        self.assertEqual(response.status_code, 200)
        self.assertIn(first.code, response.json()["answer"])
        self.assertIn(second.code, response.json()["answer"])
        self.assertIn("0 con", response.json()["answer"])
        self.assertEqual(response.json()["source_count"], 2)
        provider.assert_not_called()

    def test_counted_herd_identity_follow_ups_are_answered_directly_from_database(self):
        Herd.objects.create(
            code="CHAT-002", name="Trang trại khác", animal_type="cattle",
            management_mode="group", quantity=8, status="active",
        )
        for question in ("2 đàn đó tên là gì", "2 đàn đó là gì"):
            with self.subTest(question=question), \
                    patch("apps.ai.chat.get_configured_provider") as provider, \
                    patch("apps.ai.chat.collect_chat_facts") as collect:
                response = self.post_chat(question)
            self.assertEqual(response.status_code, 200)
            self.assertIn("CHAT-001", response.json()["answer"])
            self.assertIn("Nông trại mẫu", response.json()["answer"])
            self.assertIn("CHAT-002", response.json()["answer"])
            self.assertIn("Trang trại khác", response.json()["answer"])
            self.assertEqual(response.json()["source_count"], 2)
            provider.assert_not_called()
            collect.assert_not_called()

    def test_natural_wording_for_counted_herd_names_is_answered_from_database(self):
        Herd.objects.create(
            code="CHAT-002", name="Trang trại khác", animal_type="cattle",
            management_mode="group", quantity=8, status="active",
        )
        with patch("apps.ai.chat.get_configured_provider") as provider, \
                patch("apps.ai.chat.collect_chat_facts") as collect:
            response = self.post_chat("Tên của 2 đàn đó")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CHAT-001", response.json()["answer"])
        self.assertIn("Nông trại mẫu", response.json()["answer"])
        self.assertIn("CHAT-002", response.json()["answer"])
        self.assertIn("Trang trại khác", response.json()["answer"])
        self.assertEqual(response.json()["source_count"], 2)
        provider.assert_not_called()
        collect.assert_not_called()

    def test_herd_with_largest_recorded_quantity_is_answered_from_database(self):
        Herd.objects.create(
            code="CHAT-002", name="Trang trại khác", animal_type="cattle",
            management_mode="group", quantity=20, status="active",
        )
        with patch("apps.ai.chat.get_configured_provider") as provider, \
                patch("apps.ai.chat.collect_chat_facts") as collect:
            response = self.post_chat("Đàn có nhiều số lượng nhất")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CHAT-002", response.json()["answer"])
        self.assertIn("Trang trại khác", response.json()["answer"])
        self.assertIn("20 con", response.json()["answer"])
        self.assertNotIn("CHAT-001", response.json()["answer"])
        self.assertEqual(response.json()["source_count"], 1)
        provider.assert_not_called()
        collect.assert_not_called()

    def test_herd_with_smallest_recorded_quantity_is_answered_from_database(self):
        self.herd.quantity = 100
        self.herd.save(update_fields=("quantity",))
        Herd.objects.create(
            code="CHAT-002", name="Trang trại khác", animal_type="cattle",
            management_mode="group", quantity=20, status="active",
        )
        with patch("apps.ai.chat.get_configured_provider") as provider, \
                patch("apps.ai.chat.collect_chat_facts") as collect:
            response = self.post_chat("Đàn có số lượng ít nhất")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CHAT-002", response.json()["answer"])
        self.assertIn("Trang trại khác", response.json()["answer"])
        self.assertIn("20 con", response.json()["answer"])
        self.assertNotIn("CHAT-001", response.json()["answer"])
        self.assertEqual(response.json()["source_count"], 1)
        provider.assert_not_called()
        collect.assert_not_called()

    def test_greeting_gets_in_scope_welcome_without_database_or_provider(self):
        with patch("apps.ai.chat.get_configured_provider") as provider, \
                patch("apps.ai.chat.collect_chat_facts") as collect:
            response = self.post_chat("chào")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Chào bạn", response.json()["answer"])
        self.assertIn("tra cứu dữ liệu", response.json()["answer"])
        provider.assert_not_called()
        collect.assert_not_called()

    def test_care_schedule_direct_and_followup_never_use_care_log_or_provider(self):
        history = [
            {"role": "user", "content": "Lịch chăm sóc của đàn hiện nay là gì?"},
            {"role": "assistant", "content": "Nhật ký giả không phải lịch."},
        ]
        for question, prior in (("Lịch chăm sóc của đàn là gì?", []), ("Còn cái đó thì sao?", history), ("Còn lịch đó thì sao?", history), ("Còn lịch đó của đàn CHAT-001 thì sao?", history)):
            with self.subTest(question=question), \
                    patch("apps.ai.chat.collect_chat_facts") as collect, \
                    patch("apps.ai.chat.get_configured_provider") as provider, \
                    patch("apps.ai.chat._herd_matches") as matches:
                response = self.post_chat(question, history=prior)
            self.assertEqual(response.status_code, 200)
            self.assertIn("/care-schedules/", response.json()["answer"])
            collect.assert_not_called()
            provider.assert_not_called()
            matches.assert_not_called()

    def test_mixed_care_log_and_future_schedule_request_uses_schedule_guidance(self):
        with patch("apps.ai.chat._herd_matches") as matches, \
                patch("apps.ai.chat.collect_chat_facts") as collect, \
                patch("apps.ai.chat.get_configured_provider") as provider:
            response = self.post_chat("Nhật ký chăm sóc và lịch chăm sóc sắp tới của đàn CHAT-001 là gì?")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/care-schedules/", response.json()["answer"])
        matches.assert_not_called()
        collect.assert_not_called()
        provider.assert_not_called()

    def test_care_schedule_follow_up_chain_with_named_herd_stays_on_schedule(self):
        history = [
            {"role": "user", "content": "Lịch chăm sóc của đàn là gì?"},
            {"role": "assistant", "content": "Chatbot hiện chưa tra cứu lịch chăm sóc."},
            {"role": "user", "content": "Còn lịch đó của đàn CHAT-001 thì sao?"},
            {"role": "assistant", "content": "Chatbot hiện chưa tra cứu lịch chăm sóc."},
        ]
        with patch("apps.ai.chat._herd_matches") as matches, \
                patch("apps.ai.chat.collect_chat_facts") as collect, \
                patch("apps.ai.chat.get_configured_provider") as provider:
            response = self.post_chat("Còn cái đó thì sao?", history=history)
        self.assertEqual(response.status_code, 200)
        self.assertIn("/care-schedules/", response.json()["answer"])
        matches.assert_not_called()
        collect.assert_not_called()
        provider.assert_not_called()

    def test_recorded_care_log_question_still_uses_care_source(self):
        provider = self.fake_provider()
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat("Nhật ký chăm sóc đã ghi nhận của đàn CHAT-001 là gì?")
        self.assertEqual(response.status_code, 200)
        provider.generate.assert_called_once()
        self.assertIn("care", provider.generate.call_args.args[0].context["sources"])

    def test_off_topic_after_care_schedule_stays_rejected_before_queries(self):
        history = [{"role": "user", "content": "Lịch chăm sóc của đàn là gì?"}]
        with patch("apps.ai.chat.collect_chat_facts") as collect, \
                patch("apps.ai.chat.get_configured_provider") as provider, \
                patch("apps.ai.chat._herd_matches") as matches:
            response = self.post_chat("Giá vàng hôm nay bao nhiêu?", history=history)
        self.assertEqual(response.status_code, 200)
        self.assertIn("ngoài phạm vi", response.json()["answer"])
        collect.assert_not_called()
        provider.assert_not_called()
        matches.assert_not_called()

    def test_follow_ups_about_just_counted_herds_return_database_identities(self):
        Herd.objects.create(
            code="CHAT-002", name="Trang trại khác", animal_type="cattle",
            management_mode="group", quantity=8, status="active",
        )
        history = [
            {"role": "user", "content": "Hiện có bao nhiêu đàn"},
            {"role": "assistant", "content": "Hệ thống hiện ghi nhận 2 đàn."},
        ]
        for question in ("2 đàn đấy tên là gì", "2 đàn đấy hiện có ID là gì"):
            with self.subTest(question=question):
                with patch("apps.ai.chat.get_configured_provider") as provider, \
                        patch("apps.ai.chat.collect_chat_facts") as collect:
                    response = self.post_chat(question, history=history)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("Không tìm thấy đàn", response.json()["answer"])
                self.assertIn("CHAT-001", response.json()["answer"])
                self.assertIn("CHAT-002", response.json()["answer"])
                collect.assert_not_called()
                provider.assert_not_called()

    def test_named_herd_scopes_selected_records_to_that_herd(self):
        other_herd = Herd.objects.create(
            code="CHAT-002", name="Trang trai khac", animal_type="cattle",
            management_mode="group", quantity=8, status="active",
        )
        CareLog.objects.create(
            herd=other_herd, recorded_at="2026-06-03T08:00:00Z", activity="Other herd activity",
            notes="must not reach provider",
        )
        provider = self.fake_provider()
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat(f"Hoạt động chăm sóc của đàn {self.herd.name} là gì?")
        self.assertEqual(response.status_code, 200)
        sources = provider.generate.call_args.args[0].context["sources"]
        self.assertEqual([row["code"] for row in sources["herds"]], ["CHAT-001"])
        self.assertEqual([row["herd__code"] for row in sources["care"]], ["CHAT-001"])
        self.assertNotIn("CHAT-002", str(sources))
        self.assertNotIn("must not reach provider", str(sources))

    def test_demo_herd_code_matches_and_scopes_care_query(self):
        demo_herd = Herd.objects.create(
            code="DEMO-HERD-001", name="Demo herd", animal_type="cattle",
            management_mode="group", quantity=3, status="active",
        )
        CareLog.objects.create(
            herd=demo_herd, recorded_at="2026-06-04T08:00:00Z", activity="Demo care activity",
            notes="demo herd only",
        )
        provider = self.fake_provider()
        with patch("apps.ai.chat.get_configured_provider", return_value=provider), \
                patch("apps.ai.chat.collect_chat_facts", wraps=collect_chat_facts) as collect:
            response = self.post_chat("Hoạt động chăm sóc của đàn DEMO-HERD-001 là gì?")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Không tìm thấy đàn", response.json()["answer"])
        collect.assert_called_once_with(("herds", "care"), herd=demo_herd)
        provider.generate.assert_called_once()
        sources = provider.generate.call_args.args[0].context["sources"]
        self.assertEqual([row["code"] for row in sources["herds"]], ["DEMO-HERD-001"])
        self.assertEqual([row["herd__code"] for row in sources["care"]], ["DEMO-HERD-001"])

    def test_demo_herd_code_is_recognized_in_name_questions(self):
        demo_herd = Herd.objects.create(
            code="DEMO-HERD-001", name="Demo herd", animal_type="cattle",
            management_mode="group", quantity=3, status="active",
        )
        questions = (
            "đàn DEMO-HERD-001 tên là gì",
            "đàn DEMO-HERD-001 có tên là gì",
            "đàn DEMO-HERD-001",
        )
        for question in questions:
            with self.subTest(question=question):
                matches = _herd_matches(question)
                self.assertEqual(matches, [demo_herd])
                self.assertFalse(_has_unmatched_explicit_herd(question, matches))
                provider = self.fake_provider()
                with patch("apps.ai.chat.get_configured_provider", return_value=provider), \
                        patch("apps.ai.chat.collect_chat_facts", wraps=collect_chat_facts) as collect:
                    response = self.post_chat(question)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("Không tìm thấy đàn", response.json()["answer"])
                collect.assert_called_once_with(("herds",), herd=demo_herd)
                provider.generate.assert_called_once()
                sources = provider.generate.call_args.args[0].context["sources"]
                self.assertEqual([row["code"] for row in sources["herds"]], ["DEMO-HERD-001"])

    def test_existing_herd_code_and_name_labels_allow_question_text_after_identifier(self):
        questions = (
            f"Mã đàn {self.herd.code} hiện có bao nhiêu con?",
            f"Tên đàn {self.herd.name} hiện có bao nhiêu con?",
        )
        for question in questions:
            with self.subTest(question=question):
                provider = self.fake_provider()
                with patch("apps.ai.chat.get_configured_provider", return_value=provider) as get_provider, \
                        patch("apps.ai.chat.collect_chat_facts") as collect:
                    response = self.post_chat(question)
                self.assertEqual(response.status_code, 200)
                self.assertIn("CHAT-001", response.json()["answer"])
                self.assertIn("Nông trại mẫu", response.json()["answer"])
                self.assertIn("14 con", response.json()["answer"])
                provider.generate.assert_not_called()
                get_provider.assert_not_called()
                collect.assert_not_called()

    def test_named_herd_statistics_include_only_that_herds_records(self):
        other_herd = Herd.objects.create(
            code="CHAT-002", name="Trang trai khac", animal_type="cattle",
            management_mode="group", quantity=8, status="active",
        )
        for herd, weight, amount, opening, lost in (
            (self.herd, "100.00", "10.00", 10, 1),
            (other_herd, "900.00", "900.00", 100, 90),
        ):
            GrowthRecord.objects.create(
                target=herd, measurement_date=date(2026, 6, 1), weight=Decimal(weight),
            )
            CostRecord.objects.create(
                herd=herd, cost_date=date(2026, 6, 1), category=CostRecord.Category.FEED,
                amount=Decimal(amount),
            )
            SaleRecord.objects.create(
                target=herd, sale_date=date(2026, 6, 1), amount=Decimal(amount),
            )
            HerdLossRecord.objects.create(
                herd=herd, period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
                opening_quantity=opening, lost_quantity=lost,
            )

        provider = self.fake_provider()
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat(f"Thống kê của đàn {self.herd.code} là gì?")
        self.assertEqual(response.status_code, 200)
        provider.generate.assert_called_once()
        statistics = provider.generate.call_args.args[0].context["sources"]["statistics"]
        self.assertEqual(statistics["growth"], {
            "record_count": 1, "total_weight": "100.00", "average_weight": "100.00",
        })
        self.assertEqual(statistics["cost"], {
            "total_cost": "10.00", "by_category": {CostRecord.Category.FEED: "10.00"}, "record_count": 1,
        })
        self.assertEqual(statistics["loss"], {
            "record_count": 1, "opening_quantity": 10, "lost_quantity": 1,
            "loss_rate_percent": "10.00",
        })
        self.assertEqual(statistics["sales"], {"record_count": 1, "revenue_total": "10.00"})

    def test_generic_herd_wording_does_not_trigger_unknown_herd(self):
        for question in (
            "Đàn gia súc có những gì?", "Đàn hiện tại có bao nhiêu?", "Đàn bò của tôi?",
            "Đàn có 14 con không?",
        ):
            with self.subTest(question=question):
                provider = self.fake_provider()
                with patch("apps.ai.chat.get_configured_provider", return_value=provider):
                    response = self.post_chat(question)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("Không tìm thấy đàn", response.json()["answer"])
                provider.generate.assert_called_once()

    def test_non_herd_source_code_is_not_treated_as_an_unknown_herd_code(self):
        provider = self.fake_provider()
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat("Lịch tiêm vaccine VAX-01 gần nhất là khi nào?")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Không tìm thấy đàn", response.json()["answer"])
        provider.generate.assert_called_once()
        self.assertEqual(set(provider.generate.call_args.args[0].context["sources"]), {"vaccines"})

    def test_vaccine_due_today_question_answers_from_database_without_provider(self):
        VaccineSchedule.objects.create(
            target=self.herd, vaccine="Vaccine hôm nay", scheduled_date=date.today(),
            status=VaccineSchedule.Status.DUE,
        )
        other_herd = Herd.objects.create(
            code="CHAT-002", name="Nông trại đối chiếu", animal_type="cattle",
            management_mode="group", quantity=8, status="active",
        )
        VaccineSchedule.objects.create(
            target=other_herd, vaccine="Vaccine theo lịch", scheduled_date=date.today(),
            status=VaccineSchedule.Status.SCHEDULED,
        )
        VaccineSchedule.objects.create(
            target=self.herd, vaccine="Vaccine đã hoàn tất", scheduled_date=date.today(),
            status=VaccineSchedule.Status.COMPLETED,
        )
        for question in (
            "Đàn nào cần tiêm Vaccine hôm nay",
            "Đàn nào hôm nay cần tiêm Vaccine",
        ):
            with self.subTest(question=question), \
                    patch("apps.ai.chat.collect_chat_facts") as collect, \
                    patch("apps.ai.chat.get_configured_provider") as provider:
                response = self.post_chat(question)

            self.assertEqual(response.status_code, 200)
            answer = response.json()["answer"]
            self.assertIn("CHAT-001", answer)
            self.assertIn("Vaccine hôm nay", answer)
            self.assertIn("CHAT-002", answer)
            self.assertIn("Vaccine theo lịch", answer)
            self.assertNotIn("Vaccine đã hoàn tất", answer)
            self.assertEqual(response.json()["source_count"], 2)
            collect.assert_not_called()
            provider.assert_not_called()

    def test_unknown_named_herd_is_rejected_before_collectors_and_provider(self):
        for question in (
            "Hoạt động chăm sóc đàn UNKNOWN-999 là gì?",
            "Hoạt động chăm sóc của đàn tên không tồn tại là gì?",
            "Hoạt động chăm sóc của đàn Trang Trại Mất Tích là gì?",
            "Đàn Trang Trại Mất Tích có hoạt động chăm sóc nào?",
        ):
            with self.subTest(question=question), patch("apps.ai.chat.collect_chat_facts") as collect, \
                    patch("apps.ai.chat.get_configured_provider") as provider:
                response = self.post_chat(question)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Không tìm thấy đàn", response.json()["answer"])
            collect.assert_not_called()
            provider.assert_not_called()

    def test_existing_herd_does_not_mask_an_unknown_herd_identifier(self):
        question = f"Đàn {self.herd.code} và đàn Trang Trại Mất Tích có hoạt động chăm sóc nào?"
        with patch("apps.ai.chat.collect_chat_facts") as collect, \
                patch("apps.ai.chat.get_configured_provider") as provider:
            response = self.post_chat(question)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Không tìm thấy đàn", response.json()["answer"])
        collect.assert_not_called()
        provider.assert_not_called()

    def test_herd_reference_can_carry_from_a_recent_user_follow_up(self):
        provider = self.fake_provider()
        history = [
            {"role": "user", "content": "Hoạt động chăm sóc của đàn CHAT-001 là gì?"},
            {"role": "assistant", "content": "Có một hoạt động."},
        ]
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat("Còn cái đó thì sao?", history=history)
        self.assertEqual(response.status_code, 200)
        sources = provider.generate.call_args.args[0].context["sources"]
        self.assertEqual([row["herd__code"] for row in sources["care"]], ["CHAT-001"])

    def test_multiple_supported_sources_are_fixed_and_bounded(self):
        provider = self.fake_provider()
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat("Cho biết đàn và chuồng nào đã ghi nhận.")
        self.assertEqual(response.status_code, 200)
        sources = provider.generate.call_args.args[0].context["sources"]
        self.assertEqual(set(sources), {"herds", "pens"})
        for value in sources.values():
            self.assertLessEqual(len(value), 10)

    def test_care_source_is_serializable_and_free_text_is_bounded(self):
        CareLog.objects.create(
            herd=self.herd, recorded_at="2026-06-02T08:00:00Z", activity="Kiểm tra",
            notes="n" * 400,
        )
        provider = self.fake_provider()
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat("Nhật ký chăm sóc gần đây là gì?")
        self.assertEqual(response.status_code, 200)
        request = provider.generate.call_args.args[0]
        rows = request.context["sources"]["care"]
        self.assertEqual(len(rows[0]["notes"]), 240)
        self.assertTrue(rows[0]["notes_truncated"])
        self.assertIn(r'\"recorded_at\":\"2026-06-02T08:00:00+00:00\"', normalize_request(request)[1].decode())

    def test_out_of_scope_question_is_rejected_before_data_queries_and_provider(self):
        with patch("apps.ai.chat.collect_chat_facts") as collect, \
                patch("apps.ai.chat.get_configured_provider") as provider:
            response = self.post_chat("Giá vàng hôm nay bao nhiêu?")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ngoài phạm vi", response.json()["answer"])
        collect.assert_not_called()
        provider.assert_not_called()

    def test_follow_up_uses_prior_user_topic_and_only_that_allowlisted_source(self):
        provider = self.fake_provider()
        history = [
            {"role": "user", "content": "Cho tôi biết đàn vật nuôi nào đang được ghi nhận."},
            {"role": "assistant", "content": "Có thể có thêm thông tin về chuồng."},
        ]
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat("Còn cái đó thì sao?", history=history)
        self.assertEqual(response.status_code, 200)
        request = provider.generate.call_args.args[0]
        self.assertEqual(set(request.context["sources"]), {"herds"})
        self.assertEqual(request.context["history"], history)
        self.assertIn("untrusted", request.system_prompt.casefold())
        self.assertIn("only source", request.system_prompt.casefold())

    def test_unrelated_question_is_rejected_even_with_valid_history(self):
        history = [{"role": "user", "content": "Cho tôi biết đàn vật nuôi nào đang được ghi nhận."}]
        with patch("apps.ai.chat.collect_chat_facts") as collect, \
                patch("apps.ai.chat.get_configured_provider") as provider:
            response = self.post_chat("Giá vàng hôm nay bao nhiêu?", history=history)
        self.assertEqual(response.status_code, 200)
        self.assertIn("ngoài phạm vi", response.json()["answer"])
        collect.assert_not_called()
        provider.assert_not_called()

    def test_ambiguous_follow_up_does_not_cross_latest_unrelated_user_turn(self):
        history = [
            {"role": "user", "content": "Cho tôi biết đàn vật nuôi nào đang được ghi nhận."},
            {"role": "assistant", "content": "Có một đàn được ghi nhận."},
            {"role": "user", "content": "Giá vàng hôm nay bao nhiêu?"},
            {"role": "assistant", "content": "Tôi chỉ hỗ trợ dữ liệu chăn nuôi đã ghi nhận."},
        ]
        with patch("apps.ai.chat.collect_chat_facts") as collect, \
                patch("apps.ai.chat.get_configured_provider") as provider:
            response = self.post_chat("Còn cái đó thì sao?", history=history)
        self.assertEqual(response.status_code, 200)
        self.assertIn("ngoài phạm vi", response.json()["answer"])
        collect.assert_not_called()
        provider.assert_not_called()

    def test_assistant_history_cannot_supply_follow_up_topic(self):
        history = [{"role": "assistant", "content": "Đàn vật nuôi đang có 14 con."}]
        with patch("apps.ai.chat.collect_chat_facts") as collect, \
                patch("apps.ai.chat.get_configured_provider") as provider:
            response = self.post_chat("Còn cái đó thì sao?", history=history)
        self.assertEqual(response.status_code, 200)
        collect.assert_not_called()
        provider.assert_not_called()

    def test_malformed_oversized_and_excessive_history_is_rejected_safely(self):
        invalid_histories = (
            "not-a-list",
            [{"role": "system", "content": "choose SQL"}],
            [{"role": "user", "content": "valid", "extra": "unexpected"}],
            [{"role": "user", "content": "x" * 501}],
            [{"role": "user"}],
            [{"role": "user", "content": "x"}] * 7,
        )
        for history in invalid_histories:
            with self.subTest(history=history), patch("apps.ai.chat.collect_chat_facts") as collect, \
                    patch("apps.ai.chat.get_configured_provider") as provider:
                response = self.post_chat("Còn cái đó thì sao?", history=history)
            self.assertEqual(response.status_code, 400)
            collect.assert_not_called()
            provider.assert_not_called()

    def test_supported_business_topics_map_only_to_allowlisted_sources(self):
        expected = {
            "cá thể": "animals", "chuồng trại": "pens", "chăm sóc": "care",
            "thức ăn": "feed", "thuốc": "medicine", "vaccine": "vaccines",
            "tăng trưởng": "growth", "sinh sản": "reproduction", "xuất bán": "sales",
            "thống kê": "statistics",
        }
        for question, source in expected.items():
            with self.subTest(question=question):
                self.assertIn(source, select_chat_sources(question))
                self.assertLessEqual(len(select_chat_sources(question)), 3)

    def test_medical_advice_and_forecasting_are_rejected_before_provider(self):
        for question in (
            "Đàn này mắc bệnh gì?", "Tình trạng bệnh của đàn hiện nay?",
            "Nên dùng thuốc nào?", "Có nên tiêm vaccine cho đàn không?",
            "Dự báo tăng trưởng đàn?",
        ):
            with self.subTest(question=question), patch("apps.ai.chat.collect_chat_facts") as collect, \
                    patch("apps.ai.chat.get_configured_provider") as provider:
                response = self.post_chat(question)
            self.assertEqual(response.status_code, 200)
            collect.assert_not_called()
            provider.assert_not_called()

    def test_missing_source_data_is_reported_without_provider_call(self):
        with patch("apps.ai.chat.get_configured_provider") as provider:
            response = self.post_chat("Có những loại thức ăn nào đã ghi nhận?")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Chưa có dữ liệu đã ghi nhận về thức ăn", response.json()["answer"])
        provider.assert_not_called()

    def test_provider_failure_falls_back_to_only_the_collected_database_facts(self):
        provider = self.fake_provider(error=AIProviderError("private provider details"))
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            with self.assertLogs("apps.ai.orchestrator", level="WARNING"):
                response = self.post_chat("Đàn vật nuôi nào đang được ghi nhận?")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CHAT-001", response.json()["answer"])
        self.assertIn("Nông trại mẫu", response.json()["answer"])
        self.assertNotIn("private provider details", response.content.decode())

    def test_missing_provider_configuration_still_returns_retrieved_database_facts(self):
        with patch("apps.ai.chat.get_configured_provider", side_effect=AIConfigurationError("private config")):
            response = self.post_chat("Đàn vật nuôi nào đang được ghi nhận?")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CHAT-001", response.json()["answer"])
        self.assertNotIn("private config", response.content.decode())

    def test_invalid_provider_output_falls_back_to_only_the_collected_database_facts(self):
        provider = self.fake_provider()
        provider.generate.return_value = AIResponse("", "fake")
        before = self.snapshot()
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            with self.assertLogs("apps.ai.orchestrator", level="WARNING"):
                response = self.post_chat("Đàn vật nuôi nào đang được ghi nhận?")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AI chưa tạo được câu trả lời", response.json()["answer"])
        self.assertIn("CHAT-001", response.json()["answer"])
        self.assertIn("Nông trại mẫu", response.json()["answer"])
        self.assertEqual(response.json()["source_count"], 1)
        provider.generate.assert_called_once()
        self.assertEqual(self.snapshot(), before)

    def test_unsafe_provider_advice_is_replaced_by_safe_refusal(self):
        provider = self.fake_provider("Nên dùng thuốc X để điều trị bệnh này.")
        with patch("apps.ai.chat.get_configured_provider", return_value=provider):
            response = self.post_chat("Đàn vật nuôi nào đang được ghi nhận?")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("thuốc X", response.json()["answer"])
        self.assertIn("ngoài phạm vi", response.json()["answer"])

    def test_ai_role_matrix_and_authentication_are_enforced_before_provider(self):
        for role in (ROLE_MANAGEMENT, ROLE_TECHNICIAN):
            self.client.force_login(self.users[role])
            provider = self.fake_provider()
            with self.subTest(role=role), patch("apps.ai.chat.get_configured_provider", return_value=provider):
                response = self.post_chat("Đàn vật nuôi nào đang được ghi nhận?")
            self.assertEqual(response.status_code, 200)
            provider.generate.assert_called_once()

        for role in (ROLE_EMPLOYEE, None):
            self.client.force_login(self.users[role])
            with self.subTest(role=role), patch("apps.ai.chat.get_configured_provider") as provider:
                response = self.post_chat("Đàn vật nuôi nào đang được ghi nhận?")
            self.assertEqual(response.status_code, 403)
            provider.assert_not_called()

        self.client.logout()
        with patch("apps.ai.chat.get_configured_provider") as provider:
            response = self.post_chat("Đàn vật nuôi nào đang được ghi nhận?")
        self.assertIn(response.status_code, (401, 403))
        provider.assert_not_called()

    def test_invalid_or_oversized_question_is_rejected_before_provider(self):
        for payload in ({"question": ""}, {"question": "x" * 501},
                        {"question": "đàn vật nuôi", "context": {"secret": "private"}}):
            with self.subTest(payload=payload), patch("apps.ai.chat.get_configured_provider") as provider:
                response = self.client.post("/api/ai/chat", payload, content_type="application/json")
            self.assertEqual(response.status_code, 400)
            provider.assert_not_called()

    def test_chat_api_is_csrf_protected_for_session_clients(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.users[ROLE_MANAGEMENT])
        self.assertEqual(client.post(
            "/api/ai/chat", {"question": "Đàn vật nuôi nào?"}, content_type="application/json",
        ).status_code, 403)

