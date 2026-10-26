from apps.vaccinations.models import VaccineSchedule
from apps.vaccinations.serializers import get_alert_classification

from .orchestrator import AIOrchestrator
from .providers import get_configured_provider
from .safety import SAFETY_NOTICE, with_safety_notice
from .prompts.reminders import build_reminder_prompt
from apps.care.models import CareSchedule
from apps.care.serializers import get_care_alert_classification


AI_NOTICE = SAFETY_NOTICE
NO_DATA_NOTICE = with_safety_notice("No qualifying reminder data.")


def select_reminder_sources(scope, target_id=None, start_date=None, end_date=None):
    schedules = VaccineSchedule.objects.exclude(
        status__in=[VaccineSchedule.Status.COMPLETED, VaccineSchedule.Status.CANCELLED]
    )
    if scope == "herd":
        schedules = schedules.filter(target_id=target_id)
    if start_date:
        schedules = schedules.filter(scheduled_date__gte=start_date)
    if end_date:
        schedules = schedules.filter(scheduled_date__lte=end_date)
    return [
        {
            "target_id": schedule.target_id,
            "vaccine": schedule.vaccine,
            "scheduled_date": schedule.scheduled_date.isoformat(),
            "status": schedule.status,
            "alert_classification": get_alert_classification(schedule),
        }
        for schedule in schedules
    ]


def select_care_reminder_sources(scope, target_id=None, start_date=None, end_date=None):
    schedules = CareSchedule.objects.filter(status__in=[CareSchedule.Status.SCHEDULED, CareSchedule.Status.DUE])
    if scope == "herd":
        schedules = schedules.filter(herd_id=target_id)
    if start_date:
        schedules = schedules.filter(scheduled_date__gte=start_date)
    if end_date:
        schedules = schedules.filter(scheduled_date__lte=end_date)
    return [
        {
            "herd_id": schedule.herd_id,
            "activity": schedule.activity,
            "scheduled_date": schedule.scheduled_date.isoformat(),
            "status": schedule.status,
            "alert_classification": get_care_alert_classification(schedule),
        }
        for schedule in schedules
    ]


def generate_reminders(user, scope, target_id=None, start_date=None, end_date=None):
    sources = select_reminder_sources(scope, target_id, start_date, end_date)
    care_sources = select_care_reminder_sources(scope, target_id, start_date, end_date)
    if not sources and not care_sources:
        return {"text": "", "source_count": 0, "notice": NO_DATA_NOTICE}
    orchestrator = AIOrchestrator(get_configured_provider())
    response = orchestrator.run(user, build_reminder_prompt(), {"vaccine_schedules": sources, "care_schedules": care_sources})
    return {"text": response.text, "source_count": len(sources) + len(care_sources), "notice": AI_NOTICE}
