from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from apps.herds.models import Herd


class CareScheduleMigrationTests(TransactionTestCase):
    def test_new_table_preserves_existing_care_log_and_herd(self):
        herd = Herd.objects.create(code="MIG-HERD", name="Migration herd", animal_type="cattle", management_mode="group", quantity=5, status="active")
        executor = MigrationExecutor(connection)
        executor.migrate([("care", "0001_initial")])
        old_apps = executor.loader.project_state([("care", "0001_initial")]).apps
        CareLog = old_apps.get_model("care", "CareLog")
        log = CareLog.objects.create(herd_id=herd.pk, recorded_at="2026-01-01T00:00:00Z", activity="Existing log")
        executor = MigrationExecutor(connection)
        executor.migrate([("care", "0002_careschedule")])
        new_apps = executor.loader.project_state([("care", "0002_careschedule")]).apps
        self.assertEqual(new_apps.get_model("care", "CareLog").objects.get(pk=log.pk).activity, "Existing log")
        self.assertEqual(new_apps.get_model("herds", "Herd").objects.get(pk=herd.pk).code, "MIG-HERD")
        self.assertEqual(new_apps.get_model("care", "CareSchedule").objects.count(), 0)
