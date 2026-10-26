from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from datetime import date, timedelta

from apps.herds.models import Herd
from apps.growth.models import GrowthRecord
from apps.care.models import CareLog, CareSchedule, FeedRecord, MedicineRecord
from apps.vaccinations.models import VaccinationRecord
from apps.vaccinations.models import VaccineSchedule
from apps.users.roles import ROLE_EMPLOYEE, ROLE_MANAGEMENT, ROLE_TECHNICIAN

from .orchestrator import AIAccessDenied, AIInvocationError, AIOrchestrator
from .providers import (
    AIConfigurationError,
    AIProviderError,
    AIRequest,
    AIResponse,
    get_configured_provider,
)
from .safety import SAFETY_NOTICE
from .prompts.common import SYSTEM_PROMPT
from .prompts.herd_summary import build_herd_summary_prompt


TEST_PROMPT = build_herd_summary_prompt()


class FakeProvider:
    name = "fake"

    def __init__(self, api_key=""):
        self.api_key = api_key
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return AIResponse(text="fake result", provider=self.name)


class FailingProvider(FakeProvider):
    name = "failing"

    def generate(self, request):
        raise AIProviderError("provider failure with secret")


class StaticResponseProvider(FakeProvider):
    def __init__(self, response, api_key=""):
        super().__init__(api_key)
        self.response = response

    def generate(self, request):
        self.requests.append(request)
        return self.response


class AIOrchestratorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in (ROLE_MANAGEMENT, ROLE_TECHNICIAN, ROLE_EMPLOYEE):
            user = get_user_model().objects.create_user(username=f"ai-{role}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.no_role = get_user_model().objects.create_user(username="ai-no-role")

    def test_configured_provider_is_selected_from_environment(self):
        selected = get_configured_provider(
            {"AI_PROVIDER": "fake", "AI_API_KEY": "test-key"},
            {"fake": FakeProvider},
        )
        self.assertIsInstance(selected, FakeProvider)
        self.assertEqual(selected.api_key, "test-key")

    def test_missing_and_unsupported_provider_config_fail_safely(self):
        with self.assertRaisesRegex(AIConfigurationError, "not configured"):
            get_configured_provider({}, {"fake": FakeProvider})
        with self.assertRaisesRegex(AIConfigurationError, "not supported"):
            get_configured_provider({"AI_PROVIDER": "unknown", "AI_API_KEY": "secret"})

    def test_orchestrator_delegates_and_normalizes_response(self):
        raw_response = AIResponse(text="  fake result  ", provider="  fake  ")
        provider = StaticResponseProvider(raw_response)
        response = AIOrchestrator(provider).run(
            self.users[ROLE_MANAGEMENT], TEST_PROMPT, {"approved": "input"}
        )
        self.assertEqual(response, AIResponse(text="fake result", provider="fake"))
        self.assertIsNot(response, raw_response)
        self.assertEqual(provider.requests, [AIRequest(
            TEST_PROMPT.system_prompt, TEST_PROMPT.user_prompt, {"approved": "input"},
            TEST_PROMPT.version, TEST_PROMPT.output_constraints,
        )])

    def test_malformed_provider_outputs_are_rejected_safely(self):
        malformed = (
            None,
            {"text": "raw object", "provider": "fake"},
            AIResponse(text="", provider="fake"),
            AIResponse(text="   \n", provider="fake"),
            AIResponse(text=123, provider="fake"),
            AIResponse(text="content", provider=""),
            AIResponse(text="content", provider=123),
        )
        for raw_response in malformed:
            with self.subTest(raw_response=raw_response):
                provider = StaticResponseProvider(raw_response, "secret-token")
                with self.assertRaisesRegex(AIInvocationError, "invalid response") as raised:
                    AIOrchestrator(provider).run(
                        self.users[ROLE_MANAGEMENT], TEST_PROMPT, {"approved": "facts"}
                    )
                self.assertNotIn("secret-token", str(raised.exception))
                self.assertNotIn(repr(raw_response), str(raised.exception))

    def test_shared_prompt_boundary_contains_documented_safety_constraints(self):
        prompt = TEST_PROMPT.system_prompt
        self.assertEqual(prompt, SYSTEM_PROMPT)
        for constraint in (
            "reference information only",
            "do not diagnose",
            "do not invent",
            "insufficient",
        ):
            self.assertIn(constraint, prompt.lower())

    def test_only_explicitly_supplied_context_reaches_provider_and_no_model_is_saved(self):
        provider = FakeProvider()
        initial_herds = Herd.objects.count()
        context = {"herd_code": "H-001"}
        AIOrchestrator(provider).run(self.users[ROLE_TECHNICIAN], TEST_PROMPT, context)
        self.assertEqual(provider.requests[0].context, context)
        self.assertNotIn("password", provider.requests[0].context)
        self.assertEqual(Herd.objects.count(), initial_herds)

    def test_provider_failure_is_safe_and_does_not_log_secret(self):
        secret = "secret-api-key-123"
        provider = FailingProvider(secret)
        with self.assertLogs("apps.ai.orchestrator", level="WARNING") as logs:
            with self.assertRaisesRegex(AIInvocationError, "unavailable") as raised:
                AIOrchestrator(provider).run(self.users[ROLE_MANAGEMENT], TEST_PROMPT, {"key": "value"})
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, "\n".join(logs.output))

    def test_ai_access_reuses_approved_role_policy_and_precedence(self):
        provider = FakeProvider()
        orchestrator = AIOrchestrator(provider)
        self.assertEqual(orchestrator.run(self.users[ROLE_MANAGEMENT], TEST_PROMPT, {}).text, "fake result")
        self.assertEqual(orchestrator.run(self.users[ROLE_TECHNICIAN], TEST_PROMPT, {}).text, "fake result")
        for user in (self.users[ROLE_EMPLOYEE], self.no_role):
            with self.subTest(user=user.username):
                with self.assertRaises(AIAccessDenied):
                    orchestrator.run(user, TEST_PROMPT, {})
        multi_role = get_user_model().objects.create_user(username="ai-manager-employee")
        multi_role.groups.add(
            Group.objects.get(name=ROLE_MANAGEMENT), Group.objects.get(name=ROLE_EMPLOYEE)
        )
        self.assertEqual(orchestrator.run(multi_role, TEST_PROMPT, {}).text, "fake result")


class ReminderApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in (ROLE_MANAGEMENT, ROLE_TECHNICIAN, ROLE_EMPLOYEE):
            user = get_user_model().objects.create_user(username=f"reminder-{role}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.no_role = get_user_model().objects.create_user(username="reminder-no-role")
        cls.herd = Herd.objects.create(code="REM-1", name="Reminder herd", animal_type="cattle", management_mode="group", quantity=1, status="active")

    def post(self, user, payload):
        self.client.force_login(user)
        response = self.client.post(reverse("ai-reminders"), payload, content_type="application/json")
        self.client.logout()
        return response

    @patch("apps.ai.reminders.get_configured_provider")
    def test_reminder_selection_permissions_and_empty_state(self, factory):
        provider = FakeProvider()
        factory.return_value = provider
        empty = self.post(self.users[ROLE_MANAGEMENT], {"scope": "all"})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["result"], {"text": "", "source_count": 0})
        self.assertEqual(provider.requests, [])
        schedule = VaccineSchedule.objects.create(target=self.herd, vaccine="due", scheduled_date=date.today() + timedelta(days=2))
        VaccineSchedule.objects.create(target=self.herd, vaccine="done", scheduled_date=date.today(), status="completed")
        for user in (self.users[ROLE_MANAGEMENT], self.users[ROLE_TECHNICIAN]):
            response = self.post(user, {"scope": "herd", "target_id": self.herd.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["result"]["source_count"], 1)
        facts = provider.requests[-1].context["vaccine_schedules"]
        self.assertEqual(facts[0]["target_id"], self.herd.pk)
        self.assertEqual(facts[0]["alert_classification"], "due soon")
        self.assertNotIn("password", facts[0])
        self.assertEqual(schedule.status, "scheduled")
        for user in (self.users[ROLE_EMPLOYEE], self.no_role):
            denied = self.post(user, {"scope": "all"})
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json()["error_code"], "permission_denied")

    def test_request_validation_and_unauthenticated(self):
        self.assertIn(self.client.post(reverse("ai-reminders"), {"scope": "all"}, content_type="application/json").status_code, (401, 403))
        for payload in ({}, {"scope": "bad"}, {"scope": "herd"}, {"scope": "all", "target_id": 1}, {"scope": "all", "start_date": "bad"}, {"scope": "all", "start_date": "2026-02-02", "end_date": "2026-01-01"}):
            response = self.post(self.users[ROLE_MANAGEMENT], payload)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error_code"], "validation_error")

    @patch("apps.ai.reminders.get_configured_provider")
    def test_care_only_vaccine_only_both_and_empty_are_scoped_and_transient(self, factory):
        provider = FakeProvider()
        factory.return_value = provider
        other = Herd.objects.create(code="REM-2", name="Other", animal_type="cattle", management_mode="group", quantity=1, status="active")
        day = date.today()
        care = CareSchedule.objects.create(herd=self.herd, activity="Vệ sinh chuồng", scheduled_date=day + timedelta(days=8))
        CareSchedule.objects.create(herd=other, activity="Other herd secret", scheduled_date=day)
        CareSchedule.objects.create(herd=self.herd, activity="Completed", scheduled_date=day, status="completed")
        vaccine = VaccineSchedule.objects.create(target=self.herd, vaccine="Vaccine A", scheduled_date=day + timedelta(days=1))
        before = list(CareSchedule.objects.order_by("pk").values())
        role = self.users[ROLE_MANAGEMENT]
        care_only = self.post(role, {"scope": "herd", "target_id": self.herd.pk, "start_date": (day + timedelta(days=8)).isoformat(), "end_date": (day + timedelta(days=8)).isoformat()})
        self.assertEqual(care_only.json()["result"]["source_count"], 1)
        request = provider.requests[-1]
        self.assertEqual(request.prompt_version, "reminders-v4")
        self.assertEqual(request.context["vaccine_schedules"], [])
        self.assertEqual(request.context["care_schedules"], [{
            "herd_id": self.herd.pk, "activity": "Vệ sinh chuồng", "scheduled_date": (day + timedelta(days=8)).isoformat(),
            "status": "scheduled", "alert_classification": "scheduled-not-yet-due",
        }])
        vaccine_only = self.post(role, {"scope": "herd", "target_id": self.herd.pk, "start_date": (day + timedelta(days=1)).isoformat(), "end_date": (day + timedelta(days=1)).isoformat()})
        self.assertEqual(vaccine_only.json()["result"]["source_count"], 1)
        self.assertEqual(provider.requests[-1].context["care_schedules"], [])
        both = self.post(role, {"scope": "herd", "target_id": self.herd.pk})
        self.assertEqual(both.json()["result"]["source_count"], 2)
        self.assertEqual(len(provider.requests[-1].context["vaccine_schedules"]), 1)
        self.assertEqual(len(provider.requests[-1].context["care_schedules"]), 1)
        self.assertNotIn("Other herd secret", str(provider.requests[-1].context))
        empty = self.post(role, {"scope": "herd", "target_id": self.herd.pk, "start_date": (day + timedelta(days=2)).isoformat(), "end_date": (day + timedelta(days=2)).isoformat()})
        self.assertEqual(empty.json()["result"], {"text": "", "source_count": 0})
        self.assertEqual(len(provider.requests), 3)
        self.assertEqual(factory.call_count, 3)
        self.assertEqual(list(CareSchedule.objects.order_by("pk").values()), before)
        care.refresh_from_db()
        vaccine.refresh_from_db()
        self.assertEqual(care.status, "scheduled")
        self.assertEqual(vaccine.status, "scheduled")


class HerdSummaryApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in (ROLE_MANAGEMENT, ROLE_TECHNICIAN, ROLE_EMPLOYEE):
            user = get_user_model().objects.create_user(username=f"summary-{role}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.no_role = get_user_model().objects.create_user(username="summary-no-role")
        cls.herd = Herd.objects.create(code="SUM-1", name="Summary", animal_type="cattle", management_mode="group", quantity=4, status="active")
        cls.other_herd = Herd.objects.create(code="SUM-2", name="Other", animal_type="cattle", management_mode="group", quantity=2, status="active")
        cls.empty_herd = Herd.objects.create(code="SUM-3", name="Empty", animal_type="cattle", management_mode="group", quantity=1, status="active")
        cls.schedule = VaccineSchedule.objects.create(target=cls.herd, vaccine="vax", scheduled_date=date.today())
        CareLog.objects.create(herd=cls.herd, recorded_at="2026-01-01T00:00:00Z", activity="care")
        FeedRecord.objects.create(herd=cls.herd, recorded_at="2026-01-01T00:00:00Z", feed_type="feed", quantity="1")
        MedicineRecord.objects.create(herd=cls.herd, recorded_at="2026-01-01T00:00:00Z", medicine="med", dose="1")
        VaccinationRecord.objects.create(schedule=cls.schedule, actual_date=date.today())
        CareLog.objects.create(herd=cls.other_herd, recorded_at="2026-01-01T00:00:00Z", activity="other")

    def post(self, user, payload):
        self.client.force_login(user)
        response = self.client.post(reverse("ai-herd-summary"), payload, content_type="application/json")
        self.client.logout()
        return response

    @patch("apps.ai.herd_summary.get_configured_provider")
    def test_summary_contract_selection_permissions_and_empty(self, factory):
        provider = FakeProvider(); factory.return_value = provider
        for user in (self.users[ROLE_MANAGEMENT], self.users[ROLE_TECHNICIAN]):
            response = self.post(user, {"herd_id": self.herd.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["feature"], "herd_summary")
            self.assertEqual(response.json()["result"]["source_count"], 5)
            self.assertTrue(
                response.json()["notice"].startswith(
                    "AI-generated summary based on recorded herd data."
                )
            )
            self.assertIn(SAFETY_NOTICE, response.json()["notice"])
        facts = provider.requests[-1].context["herd_summary"]
        self.assertEqual(set(facts["herd"]), {"id", "code", "name", "animal_type", "management_mode", "quantity", "status"})
        self.assertEqual(set(facts["care_logs"][0]), {"recorded_at", "activity", "notes"})
        self.assertEqual(set(facts["feed_records"][0]), {"recorded_at", "feed_type", "quantity", "notes"})
        self.assertEqual(set(facts["medicine_records"][0]), {"recorded_at", "medicine", "dose", "notes"})
        self.assertEqual(set(facts["vaccine_schedules"][0]), {"vaccine", "scheduled_date", "status"})
        self.assertEqual(set(facts["vaccination_records"][0]), {"actual_date", "notes"})
        self.assertEqual(len(facts["care_logs"]), 1)
        self.assertNotIn("password", str(facts))
        for user in (self.users[ROLE_EMPLOYEE], self.no_role):
            self.assertEqual(self.post(user, {"herd_id": self.herd.pk}).status_code, 403)
        self.assertIn(self.client.post(reverse("ai-herd-summary"), {"herd_id": self.herd.pk}, content_type="application/json").status_code, (401, 403))
        calls_before_empty = len(provider.requests)
        empty = self.post(self.users[ROLE_MANAGEMENT], {"herd_id": self.empty_herd.pk})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["result"]["source_count"], 0)
        self.assertEqual(len(provider.requests), calls_before_empty + 1)
        self.assertTrue(all(not value for key, value in provider.requests[-1].context["herd_summary"].items() if key != "herd"))

    def test_summary_request_validation(self):
        for payload in ({}, {"herd_id": "bad"}, {"herd_id": 999999}):
            response = self.post(self.users[ROLE_MANAGEMENT], payload)
            self.assertEqual(response.status_code, 400)


class GrowthReportApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in (ROLE_MANAGEMENT, ROLE_TECHNICIAN, ROLE_EMPLOYEE):
            user = get_user_model().objects.create_user(username=f"growth-report-{role}")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.no_role = get_user_model().objects.create_user(username="growth-report-no-role")
        cls.herd = Herd.objects.create(code="GR-1", name="Growth", animal_type="cattle", management_mode="group", quantity=3, status="active")
        cls.other_herd = Herd.objects.create(code="GR-2", name="Other", animal_type="cattle", management_mode="group", quantity=2, status="active")
        cls.empty_herd = Herd.objects.create(code="GR-3", name="Empty", animal_type="cattle", management_mode="group", quantity=1, status="active")
        cls.one_herd = Herd.objects.create(code="GR-4", name="One", animal_type="cattle", management_mode="group", quantity=1, status="active")
        cls.zero_first_herd = Herd.objects.create(code="GR-5", name="Zero", animal_type="cattle", management_mode="group", quantity=1, status="active")
        for measurement_date, weight in ((date(2026, 1, 1), "10.00"), (date(2026, 1, 10), "20.00"), (date(2026, 1, 20), "40.00")):
            GrowthRecord.objects.create(target=cls.herd, measurement_date=measurement_date, weight=weight, notes="fact")
        GrowthRecord.objects.create(target=cls.other_herd, measurement_date=date(2026, 1, 10), weight="99.00", notes="exclude")
        GrowthRecord.objects.create(target=cls.one_herd, measurement_date=date(2026, 1, 1), weight="12.00")
        GrowthRecord.objects.create(target=cls.zero_first_herd, measurement_date=date(2026, 1, 1), weight="0.00")
        GrowthRecord.objects.create(target=cls.zero_first_herd, measurement_date=date(2026, 1, 2), weight="5.00")

    def post(self, user, payload):
        self.client.force_login(user)
        response = self.client.post(reverse("ai-growth-report"), payload, content_type="application/json")
        self.client.logout()
        return response

    @patch("apps.ai.growth_report.get_configured_provider")
    def test_roles_response_minimization_metrics_and_isolation(self, factory):
        provider = FakeProvider(); factory.return_value = provider
        records_before = list(
            GrowthRecord.objects.filter(target=self.herd).values_list(
                "pk", "measurement_date", "weight", "notes"
            )
        )
        for user in (self.users[ROLE_MANAGEMENT], self.users[ROLE_TECHNICIAN]):
            response = self.post(user, {"herd_id": self.herd.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.json()), {"status", "feature", "result", "notice"})
            self.assertEqual(response.json()["feature"], "growth_report")
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(set(payload["result"]), {"text", "source_count", "metrics"})
        self.assertEqual(payload["result"]["text"], "fake result")
        self.assertTrue(
            payload["notice"].startswith(
                "AI-generated growth report based on recorded growth data."
            )
        )
        self.assertIn(SAFETY_NOTICE, payload["notice"])
        self.assertEqual(payload["result"]["source_count"], 3)
        metrics = payload["result"]["metrics"]
        self.assertEqual(metrics["record_count"], 3)
        self.assertEqual(metrics["first_measurement_date"], "2026-01-01")
        self.assertAlmostEqual(float(metrics["first_weight"]), 10.0)
        self.assertEqual(metrics["last_measurement_date"], "2026-01-20")
        self.assertAlmostEqual(float(metrics["last_weight"]), 40.0)
        self.assertAlmostEqual(float(metrics["absolute_change"]), 30.0)
        self.assertAlmostEqual(float(metrics["percent_change"]), 300.0)
        self.assertAlmostEqual(float(metrics["average_weight"]), 70 / 3)
        context = provider.requests[-1].context
        self.assertEqual(set(context), {"herd", "growth_records", "metrics"})
        self.assertEqual(set(context["herd"]), {"id", "code", "name"})
        self.assertTrue(all(set(item) == {"measurement_date", "weight", "notes"} for item in context["growth_records"]))
        self.assertNotIn("99.00", str(context))
        for forbidden in ("password", "groups", "care_logs", "sales", "statistics", "api_key"):
            self.assertNotIn(forbidden, str(context).lower())
        request = provider.requests[-1]
        prompt = " ".join((request.system_prompt, request.user_prompt, *request.output_constraints)).lower()
        self.assertIn("do not invent", prompt)
        self.assertIn("forecast", prompt)
        self.assertIn("diagnose", prompt)
        self.assertEqual(
            records_before,
            list(
                GrowthRecord.objects.filter(target=self.herd).values_list(
                    "pk", "measurement_date", "weight", "notes"
                )
            ),
        )
        for user in (self.users[ROLE_EMPLOYEE], self.no_role):
            denied = self.post(user, {"herd_id": self.herd.pk})
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json()["error_code"], "permission_denied")
        self.assertIn(self.client.post(reverse("ai-growth-report"), {"herd_id": self.herd.pk}, content_type="application/json").status_code, (401, 403))

    @patch("apps.ai.growth_report.get_configured_provider")
    def test_independent_and_inclusive_date_filters(self, factory):
        provider = FakeProvider(); factory.return_value = provider
        cases = (
            ({"start_date": "2026-01-10"}, ["2026-01-10", "2026-01-20"]),
            ({"end_date": "2026-01-10"}, ["2026-01-01", "2026-01-10"]),
            ({"start_date": "2026-01-01", "end_date": "2026-01-10"}, ["2026-01-01", "2026-01-10"]),
        )
        for filters, expected in cases:
            response = self.post(self.users[ROLE_MANAGEMENT], {"herd_id": self.herd.pk, **filters})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row["measurement_date"] for row in provider.requests[-1].context["growth_records"]], expected)

    def test_request_validation(self):
        for payload in ({}, {"herd_id": "bad"}, {"herd_id": 999999}, {"herd_id": self.herd.pk, "start_date": "2026-02-01", "end_date": "2026-01-01"}):
            response = self.post(self.users[ROLE_MANAGEMENT], payload)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error_code"], "validation_error")

    @patch("apps.ai.growth_report.get_configured_provider")
    def test_insufficient_data_skips_provider_and_zero_first_weight(self, factory):
        for herd, expected_count in ((self.empty_herd, 0), (self.one_herd, 1)):
            response = self.post(self.users[ROLE_MANAGEMENT], {"herd_id": herd.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["result"]["source_count"], expected_count)
            self.assertEqual(response.json()["result"]["text"], "")
            self.assertTrue(
                response.json()["notice"].startswith(
                    "Insufficient growth data to generate an AI growth report."
                )
            )
            self.assertIn(SAFETY_NOTICE, response.json()["notice"])
        factory.assert_not_called()
        provider = FakeProvider(); factory.return_value = provider
        response = self.post(self.users[ROLE_MANAGEMENT], {"herd_id": self.zero_first_herd.pk})
        self.assertIsNone(response.json()["result"]["metrics"]["percent_change"])

    @patch("apps.ai.growth_report.get_configured_provider")
    def test_provider_failure_is_safe_and_does_not_mutate_records(self, factory):
        factory.return_value = FailingProvider("secret-growth-key")
        before = list(GrowthRecord.objects.filter(target=self.herd).values_list("pk", "weight", "notes"))
        response = self.post(self.users[ROLE_MANAGEMENT], {"herd_id": self.herd.pk})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error_code"], "ai_provider_failure")
        self.assertNotIn("secret-growth-key", str(response.json()))
        self.assertNotIn("provider failure", str(response.json()))
        self.assertEqual(before, list(GrowthRecord.objects.filter(target=self.herd).values_list("pk", "weight", "notes")))


class AIOutputSafetyApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = get_user_model().objects.create_user(username="safety-manager")
        cls.manager.groups.add(Group.objects.get(name=ROLE_MANAGEMENT))
        cls.herd = Herd.objects.create(
            code="SAFE-1",
            name="Safety herd",
            animal_type="cattle",
            management_mode="group",
            quantity=2,
            status="active",
        )
        cls.schedule = VaccineSchedule.objects.create(
            target=cls.herd,
            vaccine="safety-vaccine",
            scheduled_date=date.today() + timedelta(days=1),
        )
        GrowthRecord.objects.create(
            target=cls.herd,
            measurement_date=date(2026, 1, 1),
            weight="10.00",
        )
        GrowthRecord.objects.create(
            target=cls.herd,
            measurement_date=date(2026, 1, 2),
            weight="12.00",
        )

    def post(self, route, payload):
        self.client.force_login(self.manager)
        response = self.client.post(reverse(route), payload, content_type="application/json")
        self.client.logout()
        return response

    @patch("apps.ai.reminders.get_configured_provider")
    @patch("apps.ai.herd_summary.get_configured_provider")
    @patch("apps.ai.growth_report.get_configured_provider")
    def test_valid_output_and_safety_notice_integrate_with_all_features(
        self, growth_factory, summary_factory, reminder_factory
    ):
        providers = {
            "ai-reminders": StaticResponseProvider(
                AIResponse(text="  reminder text  ", provider=" fake ")
            ),
            "ai-herd-summary": StaticResponseProvider(
                AIResponse(text="  summary text  ", provider=" fake ")
            ),
            "ai-growth-report": StaticResponseProvider(
                AIResponse(text="  growth text  ", provider=" fake ")
            ),
        }
        reminder_factory.return_value = providers["ai-reminders"]
        summary_factory.return_value = providers["ai-herd-summary"]
        growth_factory.return_value = providers["ai-growth-report"]
        requests = (
            ("ai-reminders", {"scope": "herd", "target_id": self.herd.pk}, "reminder text"),
            ("ai-herd-summary", {"herd_id": self.herd.pk}, "summary text"),
            ("ai-growth-report", {"herd_id": self.herd.pk}, "growth text"),
        )
        for route, request_payload, expected_text in requests:
            with self.subTest(route=route):
                response = self.post(route, request_payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["result"]["text"], expected_text)
                self.assertIn(SAFETY_NOTICE, response.json()["notice"])
                self.assertEqual(providers[route].requests[-1].system_prompt, SYSTEM_PROMPT)

    @patch("apps.ai.herd_summary.get_configured_provider")
    def test_malformed_output_uses_safe_error_envelope(self, factory):
        raw_secret = "provider-secret-token-at-internal-path"
        factory.return_value = StaticResponseProvider(
            {"text": raw_secret, "provider": object()}, raw_secret
        )
        response = self.post("ai-herd-summary", {"herd_id": self.herd.pk})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            set(response.json()),
            {"error_code", "message"},
        )
        self.assertEqual(response.json()["error_code"], "ai_invalid_response")
        rendered = str(response.json())
        self.assertNotIn(raw_secret, rendered)
        self.assertNotIn("Traceback", rendered)
        self.assertNotIn("apps.ai", rendered)

    @patch("apps.ai.growth_report.get_configured_provider")
    def test_provider_text_cannot_override_application_owned_facts(self, factory):
        injected_text = (
            '<script>alert("xss")</script> '
            '{"source_count":999,"metrics":{"record_count":999}}'
        )
        provider = StaticResponseProvider(AIResponse(text=injected_text, provider="fake"))
        factory.return_value = provider
        before = list(
            GrowthRecord.objects.filter(target=self.herd).values_list(
                "pk", "measurement_date", "weight", "notes"
            )
        )
        response = self.post("ai-growth-report", {"herd_id": self.herd.pk})
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["text"], injected_text)
        self.assertEqual(result["source_count"], 2)
        self.assertEqual(result["metrics"]["record_count"], 2)
        self.assertAlmostEqual(float(result["metrics"]["absolute_change"]), 2.0)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.status, VaccineSchedule.Status.SCHEDULED)
        self.assertEqual(
            provider.requests[-1].context["growth_records"][0]["weight"],
            GrowthRecord.objects.filter(target=self.herd)
            .order_by("measurement_date", "pk")
            .first()
            .weight,
        )
        self.assertEqual(
            before,
            list(
                GrowthRecord.objects.filter(target=self.herd).values_list(
                    "pk", "measurement_date", "weight", "notes"
                )
            ),
        )
