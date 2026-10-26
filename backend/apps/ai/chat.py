"""Constrained, read-only chat over explicitly selected livestock data sources."""

import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Q, Sum

from apps.care.models import CareLog, CareSchedule, FeedRecord, MedicineRecord
from apps.growth.models import GrowthRecord
from apps.herds.models import Animal, AnimalGroup, Herd
from apps.pens.models import Pen
from apps.reproduction.models import ReproductionRecord
from apps.sales.models import SaleRecord
from apps.domain_validation import derive_sales_revenue
from apps.statistics.models import CostRecord, HerdLossRecord
from apps.statistics.services import get_cost_statistics, get_growth_statistics, get_loss_statistics
from apps.vaccinations.models import VaccinationRecord, VaccineSchedule

from .orchestrator import AIInvocationError, AIOrchestrator
from .providers import AIConfigurationError, get_configured_provider
from .prompts.chat import build_chat_prompt
from .safety import with_safety_notice


MAX_RECORDS_PER_SOURCE = 10
MAX_NOTE_LENGTH = 240
HERD_NOT_FOUND_ANSWER = "Không tìm thấy đàn được nêu. Vui lòng kiểm tra mã/tên đàn hoặc làm rõ câu hỏi."
CHAT_NOTICE = with_safety_notice(
    "Câu trả lời chỉ tổng hợp dữ liệu đã ghi nhận trong hệ thống."
)
OUT_OF_SCOPE_ANSWER = (
    "Mình chỉ hỗ trợ hỏi đáp về dữ liệu chăn nuôi đã ghi nhận trong hệ thống; "
    "câu hỏi này nằm ngoài phạm vi đó hoặc yêu cầu tư vấn chuyên môn."
)
CARE_SCHEDULE_ANSWER = (
    "Mình có thể tra cứu lịch chăm sóc đã lưu. Hãy nêu rõ thời gian (hôm nay, sắp tới, quá hạn), "
    "trạng thái (đã hoàn thành/đã hủy), hoặc yêu cầu liệt kê tất cả. Bạn cũng có thể mở "
    "Lịch chăm sóc (/care-schedules/) hoặc chức năng Nhắc lịch trong AI Assistant."
)
CARE_SCHEDULE_MIXED_ANSWER = (
    "Câu hỏi đang gộp nhật ký chăm sóc đã ghi nhận với lịch chăm sóc. Chatbot chưa gộp hai loại "
    "trong một câu trả lời; vui lòng hỏi riêng về lịch tại /care-schedules/ hoặc dùng Nhắc lịch."
)

# Matching is deterministic and happens before any source query. The chat model
# cannot choose a model, field, filter, relation, or query.
SOURCE_TERMS = {
    "herds": ("dan", "vat nuoi", "loai vat nuoi", "so luong dan"),
    "animals": ("ca the", "ma ca the", "con vat"),
    "animal_groups": ("nhom vat nuoi", "nhom dan"),
    "pens": ("chuong", "chuong trai"),
    "care": ("cham soc", "nhat ky cham soc", "hoat dong cham soc"),
    "feed": ("thuc an", "cho an", "luong an"),
    "medicine": ("thuoc", "thuoc da dung", "lieu luong"),
    "vaccines": ("vaccine", "vac xin", "tiem phong", "lich tiem", "lan tiem"),
    "growth": ("tang truong", "can nang", "lan can", "khoi luong"),
    "reproduction": ("sinh san", "phoi giong", "su kien sinh san"),
    "sales": ("xuat ban", "ban vat nuoi", "doanh thu", "tien ban"),
    "statistics": ("thong ke", "chi phi", "hao hut", "ty le hao hut", "so lieu tong hop"),
}
OUT_OF_SCOPE_TERMS = (
    "gia vang", "gia bac", "thoi tiet", "du bao thoi tiet", "tin tuc", "thoi su",
    "chung khoan", "ty gia", "ket qua bong da", "chan doan", "benh", "trieu chung",
    "co benh khong", "dieu tri", "ke don", "nen dung", "nen dung thuoc", "nen tiem",
    "co nen", "khuyen nghi", "loi khuyen", "phac do", "tien luong",
    "du doan", "du bao",
)
UNSAFE_ANSWER_TERMS = (
    "chan doan", "dieu tri", "ke don", "nen dung", "nen tiem", "khuyen nghi",
    "loi khuyen", "phac do", "tien luong", "du doan", "du bao",
)
SOURCE_LABELS = {
    "herds": "đàn vật nuôi",
    "animals": "cá thể",
    "animal_groups": "nhóm vật nuôi",
    "pens": "chuồng trại",
    "care": "chăm sóc",
    "feed": "thức ăn",
    "medicine": "thuốc đã ghi nhận",
    "vaccines": "vaccine và lần tiêm",
    "growth": "tăng trưởng",
    "reproduction": "sinh sản",
    "sales": "xuất bán",
    "statistics": "thống kê",
}
FOLLOW_UP_CUES = (
    " con do ", " dan do ", " cai do ", " no thi sao ", " vay thi sao ",
    " con the nao ", " con bao nhieu ", " the nao nua ", " con cai nao ",
    " con so lieu ", " con phan do ", " con muc do ",
)
def _normalize_question(question):
    value = unicodedata.normalize("NFD", question.casefold())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    value = value.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def select_chat_sources(question):
    normalized = _normalize_question(question)
    padded = f" {normalized} "
    if any(f" {term} " in padded for term in OUT_OF_SCOPE_TERMS):
        return ()
    selected = tuple(
        source for source, terms in SOURCE_TERMS.items()
        if any(f" {unicodedata.normalize('NFD', term).encode('ascii', 'ignore').decode().casefold()} " in padded
               for term in terms)
    )
    # Avoid turning a general or mixed unsupported request into a broad scan.
    if not selected or len(selected) > 3:
        return ()
    return selected


def _resolve_chat_sources(question, history):
    """Resolve only clear follow-ups from prior user questions; never from AI text."""
    normalized = _normalize_question(question)
    padded = f" {normalized} "
    if _is_explicitly_out_of_scope(padded):
        return ()
    sources = select_chat_sources(question)
    if sources:
        return sources
    if not _is_clear_follow_up(padded):
        return ()
    for message in reversed(history):
        if message["role"] != "user":
            continue
        prior_question = message["content"]
        prior_padded = f" {_normalize_question(prior_question)} "
        if _is_explicitly_out_of_scope(prior_padded):
            return ()
        prior_sources = select_chat_sources(prior_question)
        if prior_sources:
            return prior_sources
        if not _is_clear_follow_up(prior_padded):
            return ()
    return ()


def _is_explicitly_out_of_scope(padded_question):
    return any(f" {term} " in padded_question for term in OUT_OF_SCOPE_TERMS)


def _is_clear_follow_up(padded_question):
    return any(cue in padded_question for cue in FOLLOW_UP_CUES)


def _is_care_schedule_request(question):
    padded = f" {_normalize_question(question)} "
    return any(phrase in padded for phrase in (
        " lich cham soc ", " ke hoach cham soc ", " cham soc sap toi ",
    ))


def _is_care_schedule_follow_up_cue(padded_question):
    return _is_clear_follow_up(padded_question) or _is_care_schedule_specific_follow_up_cue(padded_question)


def _is_care_schedule_specific_follow_up_cue(padded_question):
    return any(phrase in padded_question for phrase in (
        " con lich do ", " lich do ", " lich ay ", " con hom nay ", " con sap toi ",
        " con qua han ", " con da hoan thanh ", " con da huy ",
        " ngay mai ", " ngay kia ", " thang sau ", " thang toi ", " tuan sau ", " tuan toi ",
    ))


def _has_unsupported_care_schedule_time(question, padded_question):
    unsupported_phrases = (
        " ngay mai ", " ngay kia ", " ngay mot ", " thang nay ", " thang sau ", " thang toi ",
        " thang truoc ", " tuan nay ", " tuan sau ", " tuan toi ", " tuan truoc ",
        " nam nay ", " nam sau ", " nam truoc ", " dau thang ", " cuoi thang ",
    )
    if any(phrase in padded_question for phrase in unsupported_phrases):
        return True
    has_human_numeric_date = (
        (" hom nay " not in padded_question and re.search(r"\bngay\s+\d{1,2}\b", padded_question))
        or re.search(r"\bthang\s+\d{1,2}\b", padded_question)
    )
    has_explicit_numeric_date = re.search(
        r"(?<![\w])(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?)(?![\w])",
        question,
    )
    if has_human_numeric_date or has_explicit_numeric_date:
        return True
    return False


def _care_schedule_constraints(question):
    padded = f" {_normalize_question(question)} "
    date_filters = [
        ("upcoming", " sap toi " in padded or " sap den " in padded),
        ("today", " hom nay " in padded),
        ("overdue", " qua han " in padded),
    ]
    status_filters = [
        ("completed", any(term in padded for term in (" hoan thanh ", " hoan tat ", " da thuc hien "))),
        ("cancelled", any(term in padded for term in (" da huy ", " huy bo "))),
    ]
    count_requested = any(term in padded for term in (" bao nhieu ", " dem ", " so luong lich "))
    list_requested = any(term in padded for term in (" liet ke ", " danh sach ", " cho xem "))
    all_requested = any(term in padded for term in (" tat ca ", " toan bo "))
    dates = [name for name, present in date_filters if present]
    statuses = [name for name, present in status_filters if present]
    return {
        "date_filter": dates[0] if len(dates) == 1 else None,
        "status": statuses[0] if len(statuses) == 1 else None,
        "operation": "count" if count_requested else "list" if list_requested else None,
        "all_requested": all_requested,
        "unsupported_time": _has_unsupported_care_schedule_time(question, padded),
        "ambiguous": len(dates) > 1 or len(statuses) > 1 or count_requested and list_requested,
    }


def _merge_care_schedule_constraints(base, override):
    merged_status = (
        None if override["all_requested"] and override["status"] is None
        else override["status"] if override["status"] is not None
        else base["status"]
    )
    return {
        "date_filter": override["date_filter"] if override["date_filter"] is not None else base["date_filter"],
        "status": merged_status,
        "operation": override["operation"] if override["operation"] is not None else base["operation"],
    } | {"all_requested": base["all_requested"] or override["all_requested"],
         "unsupported_time": base["unsupported_time"] or override["unsupported_time"],
         "ambiguous": base["ambiguous"] or override["ambiguous"]}


def _finalize_care_schedule_query(constraints):
    if constraints["ambiguous"] or constraints["unsupported_time"]:
        return None
    operation = constraints["operation"]
    if operation is None and (constraints["date_filter"] or constraints["status"] or constraints["all_requested"]):
        operation = "list"
    if operation is None:
        return None
    return {**constraints, "operation": operation}


def _care_schedule_query_for_question(question, history):
    padded = f" {_normalize_question(question)} "
    has_topic = _is_care_schedule_request(question)
    clarify_care_follow_up = _is_care_schedule_specific_follow_up_cue(padded)
    mentions_journal = " nhat ky " in padded or " hoat dong cham soc da ghi nhan " in padded
    if has_topic and mentions_journal:
        return "mixed", None
    if has_topic:
        direct = _finalize_care_schedule_query(_care_schedule_constraints(question))
        if direct:
            return "query", direct
        if not _is_care_schedule_follow_up_cue(padded):
            return "clarify", None

    if not _is_care_schedule_follow_up_cue(padded):
        return ("clarify", None) if has_topic else (None, None)
    selected = select_chat_sources(question)
    if selected and (selected != ("herds",) or " lich " not in padded):
        return ("clarify", None) if has_topic else (None, None)

    overrides = _care_schedule_constraints(question)
    for message in reversed(history):
        if message["role"] != "user":
            continue
        prior = message["content"]
        prior_padded = f" {_normalize_question(prior)} "
        if _is_explicitly_out_of_scope(prior_padded):
            return ("clarify", None) if has_topic or clarify_care_follow_up else (None, None)
        prior_has_topic = _is_care_schedule_request(prior)
        prior_is_mixed = prior_has_topic and (
            " nhat ky " in prior_padded or " hoat dong cham soc da ghi nhan " in prior_padded
        )
        if prior_is_mixed:
            return "mixed", None
        if prior_has_topic:
            prior_constraints = _care_schedule_constraints(prior)
            prior_query = _finalize_care_schedule_query(prior_constraints)
            if prior_query:
                query = _finalize_care_schedule_query(
                    _merge_care_schedule_constraints(prior_query, overrides)
                )
                return ("query", query) if query else ("clarify", None)
            if not prior_constraints["ambiguous"]:
                inherited_query = _finalize_care_schedule_query(
                    _merge_care_schedule_constraints(prior_constraints, overrides)
                )
                if inherited_query:
                    return "query", inherited_query
            if not _is_care_schedule_follow_up_cue(prior_padded):
                return "clarify", None
        else:
            prior_sources = select_chat_sources(prior)
            prior_follow_up = _is_care_schedule_follow_up_cue(prior_padded)
            if prior_sources and (prior_sources != ("herds",) or " lich " not in prior_padded):
                return ("clarify", None) if has_topic or clarify_care_follow_up else (None, None)
            if not prior_follow_up:
                return ("clarify", None) if has_topic or clarify_care_follow_up else (None, None)
        overrides = _merge_care_schedule_constraints(_care_schedule_constraints(prior), overrides)
    return ("clarify", None) if has_topic or clarify_care_follow_up else (None, None)


def _query_care_schedules(question, history, query):
    herd, herd_not_found = _resolve_chat_herd(question, history, care_schedule_follow_up=True)
    if herd_not_found:
        return {"answer": HERD_NOT_FOUND_ANSWER, "notice": CHAT_NOTICE, "source_count": 0}

    today = date.today()
    schedules = CareSchedule.objects.select_related("herd").all()
    if herd is not None:
        schedules = schedules.filter(herd=herd)
    start_date = end_date = None
    if query["date_filter"] == "upcoming":
        start_date, end_date = today + timedelta(days=1), today + timedelta(days=7)
        schedules = schedules.filter(scheduled_date__gte=start_date, scheduled_date__lte=end_date)
    elif query["date_filter"] == "today":
        start_date = end_date = today
        schedules = schedules.filter(scheduled_date=today)
    elif query["date_filter"] == "overdue":
        start_date, end_date = None, today
        schedules = schedules.filter(scheduled_date__lt=today)

    if query["status"]:
        schedules = schedules.filter(status=query["status"])
    elif query["date_filter"]:
        schedules = schedules.filter(status__in=[CareSchedule.Status.SCHEDULED, CareSchedule.Status.DUE])
    elif query["operation"] == "count" and not query["all_requested"]:
        schedules = schedules.filter(status__in=[CareSchedule.Status.SCHEDULED, CareSchedule.Status.DUE])

    total_count = schedules.count()
    label = _care_schedule_query_label(query, today, start_date, end_date, herd)
    if not total_count:
        answer = f"Không có lịch chăm sóc phù hợp với điều kiện đã hỏi ({label})."
        return {"answer": answer, "notice": CHAT_NOTICE, "source_count": 0}
    if query["operation"] == "count":
        return {"answer": f"Có {total_count} lịch chăm sóc phù hợp với điều kiện đã hỏi ({label}).",
                "notice": CHAT_NOTICE, "source_count": total_count}

    rows = schedules.order_by("scheduled_date", "herd__code", "pk").values(
        "herd__code", "herd__name", "activity", "scheduled_date", "status",
    )[:MAX_RECORDS_PER_SOURCE]
    entries = []
    for row in rows:
        status_label = dict(CareSchedule.Status.choices).get(row["status"], row["status"])
        entries.append(
            f"{row['herd__code']} — {row['herd__name']}; {row['activity']}; "
            f"ngày {row['scheduled_date'].isoformat()}; trạng thái {status_label} ({row['status']})"
        )
    answer = f"Lịch chăm sóc phù hợp ({label}): " + " | ".join(entries)
    if total_count > len(entries):
        answer += f". Đang hiển thị {len(entries)} trên tổng {total_count} lịch phù hợp."
    else:
        answer += "."
    return {"answer": answer, "notice": CHAT_NOTICE, "source_count": total_count}


def _care_schedule_query_label(query, today, start_date, end_date, herd):
    date_filter = query["date_filter"]
    if date_filter == "upcoming":
        date_label = f"ngày từ {start_date.isoformat()} đến hết {end_date.isoformat()}"
    elif date_filter == "today":
        date_label = f"ngày hôm nay ({today.isoformat()})"
    elif date_filter == "overdue":
        date_label = f"ngày trước {today.isoformat()}"
    else:
        date_label = "mọi ngày"
    if query["status"] == "completed":
        status_label = "trạng thái đã thực hiện (completed)"
    elif query["status"] == "cancelled":
        status_label = "trạng thái đã hủy (cancelled)"
    elif query["status"]:
        status_label = dict(CareSchedule.Status.choices).get(query["status"], query["status"])
    elif date_filter or (query["operation"] == "count" and not query["all_requested"]):
        status_label = "nhóm scheduled/due (chưa hoàn thành, chưa hủy)"
    else:
        status_label = "mọi trạng thái"
    herd_label = f"đàn {herd.code} — {herd.name}" if herd is not None else "mọi đàn"
    return f"{date_label}; {status_label}; {herd_label}"


def _is_care_schedule_follow_up(question, history):
    padded = f" {_normalize_question(question)} "
    if not _is_care_schedule_follow_up_cue(padded):
        return False
    sources = select_chat_sources(question)
    if sources and (sources != ("herds",) or " lich " not in padded):
        return False
    for message in reversed(history):
        if message["role"] != "user":
            continue
        prior = message["content"]
        if _is_explicitly_out_of_scope(f" {_normalize_question(prior)} "):
            return False
        if _is_care_schedule_request(prior):
            return True
        if not _is_care_schedule_follow_up_cue(f" {_normalize_question(prior)} "):
            return False
    return False


def _is_herd_count_question(question):
    normalized = f" {_normalize_question(question)} "
    return any(term in normalized for term in (" bao nhieu dan ", " tong so dan ", " so luong dan "))


def _is_herd_quantity_question(question):
    normalized = f" {_normalize_question(question)} "
    return " bao nhieu con " in normalized or " so luong " in normalized


def _is_vaccine_due_today_question(question):
    normalized = f" {_normalize_question(question)} "
    return " hom nay " in normalized and any(
        term in normalized for term in (" vaccine ", " vac xin ", " tiem phong ", " lich tiem ")
    ) and any(term in normalized for term in (" can tiem ", " den han ", " lich tiem ", " tiem "))


def _is_greeting(question):
    return _normalize_question(question) in {"chao", "xin chao", "chao ban", "xin chao ban", "hello", "hi"}


def _is_counted_herd_list_question(question):
    normalized = f" {_normalize_question(question)} "
    refers_to_counted_herds = re.search(r"\b(?:\d+|hai)\s+dan\s+(?:do|day)\b", normalized)
    asks_for_identity = (
        re.search(r"\bten\b", normalized) is not None
        or any(term in normalized for term in (" ma gi ", " id gi ", " la gi "))
    )
    return bool(refers_to_counted_herds and asks_for_identity)


def _is_largest_herd_quantity_question(question):
    normalized = f" {_normalize_question(question)} "
    asks_for_largest = (
        re.search(r"\bnhieu\b.*\bnhat\b", normalized) is not None
        or any(term in normalized for term in (" lon nhat ", " cao nhat ", " dong nhat "))
    )
    return asks_for_largest


def _is_smallest_herd_quantity_question(question):
    normalized = f" {_normalize_question(question)} "
    asks_for_smallest = (
        re.search(r"\bit\b.*\bnhat\b", normalized) is not None
        or any(term in normalized for term in (" it con nhat ", " thap nhat ", " nho nhat "))
    )
    return asks_for_smallest


def _herd_matches(question):
    normalized = f" {_normalize_question(question)} "
    matched = []
    for herd in Herd.objects.only("pk", "code", "name").order_by("pk"):
        for identifier in (herd.code, herd.name):
            identifier = f" {_normalize_question(identifier)} "
            if identifier.strip() and identifier in normalized:
                matched.append(herd)
                break
    return matched


def _has_unmatched_explicit_herd(question, matches=()):
    normalized = f" {_normalize_question(question)} "
    known_ids = {
        _normalize_question(identifier)
        for herd in matches for identifier in (herd.code, herd.name)
    }

    # Explicit labels disambiguate arbitrary code/name formats without imposing
    # a format on Herd.code. Compare the labeled value when a known herd also
    # appears elsewhere in the same question.
    for marker in (" dan ten ", " ten dan ", " ma dan "):
        search_from = 0
        while (marker_at := normalized.find(marker, search_from)) >= 0:
            candidate = normalized[marker_at + len(marker):].strip()
            if candidate and not any(
                candidate == identifier or candidate.startswith(f"{identifier} ")
                for identifier in known_ids
            ):
                return True
            search_from = marker_at + len(marker)

    # Only treat a separated token as a herd code when it follows "đàn".
    # Other codes in the question may identify records from another source.
    for token in re.findall(r"(?<!\w)(?i:đàn)\s+([\w]+(?:[-_][\w]+)+)(?!\w)", question):
        if _normalize_question(token) not in known_ids:
            return True

    # Treat a title-cased phrase as an explicit name. Check Unicode casing on
    # the actual first character instead of a broad [A-ZÀ-Ỵ] range, which also
    # contains many lowercase Vietnamese letters such as "đ".
    for match in re.finditer(r"(?<!\w)(?i:đàn)\s+([^\W\d_]+(?:\s+[^\W\d_]+)*)", question):
        words = match.group(1).split()
        if not words or not words[0][0].isupper():
            continue
        title_words = [words[0]]
        for word in words[1:]:
            if not word[0].isupper():
                break
            title_words.append(word)
        candidate = _normalize_question(" ".join(title_words))
        if not any(identifier == candidate or identifier.startswith(f"{candidate} ")
                   for identifier in known_ids):
            # A title-cased first code segment is handled by the full code token above.
            candidate_end = match.start(1) + len(" ".join(title_words))
            following = question[candidate_end:candidate_end + 1]
            if following not in ("-", "_"):
                return True
    return False


def _resolve_chat_herd(question, history, *, care_schedule_follow_up=False):
    matches = _herd_matches(question)
    if _has_unmatched_explicit_herd(question, matches):
        return None, True
    if matches:
        unique = {herd.pk: herd for herd in matches}
        return (next(iter(unique.values())), False) if len(unique) == 1 else (None, True)
    follow_up_cue = _is_care_schedule_follow_up_cue if care_schedule_follow_up else _is_clear_follow_up
    if not follow_up_cue(f" {_normalize_question(question)} "):
        return None, False
    for message in reversed(history):
        if message["role"] != "user":
            continue
        prior = message["content"]
        prior_padded = f" {_normalize_question(prior)} "
        if _is_explicitly_out_of_scope(prior_padded):
            return None, False
        matches = _herd_matches(prior)
        if _has_unmatched_explicit_herd(prior, matches):
            return None, True
        if matches:
            unique = {herd.pk: herd for herd in matches}
            return (next(iter(unique.values())), False) if len(unique) == 1 else (None, True)
        if not follow_up_cue(prior_padded):
            return None, False
    return None, False


def _answer_requests_professional_advice(answer):
    normalized = _normalize_question(answer)
    padded = f" {normalized} "
    return any(f" {term} " in padded for term in UNSAFE_ANSWER_TERMS)


def _limited(queryset, fields, ordering):
    rows = queryset.order_by(*ordering).values(*fields)[:MAX_RECORDS_PER_SOURCE]
    return [
        {key: value.isoformat() if hasattr(value, "isoformat") else value
         for key, value in row.items()}
        for row in rows
    ]


def _collect_statistics(herd=None):
    if herd is None:
        return {
            "growth": get_growth_statistics(),
            "cost": {**get_cost_statistics(), "record_count": CostRecord.objects.count()},
            "loss": get_loss_statistics(),
            "sales": {
                "record_count": SaleRecord.objects.count(),
                "revenue_total": format(derive_sales_revenue(SaleRecord.objects.all()), ".2f"),
            },
        }

    growth = GrowthRecord.objects.filter(target=herd)
    growth_values = growth.aggregate(count=Count("id"), total=Sum("weight"), average=Avg("weight"))
    costs = CostRecord.objects.filter(herd=herd)
    cost_total = costs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    cost_by_category = {
        row["category"]: format(row["total"], ".2f")
        for row in costs.values("category").annotate(total=Sum("amount")).order_by("category")
    }
    losses = HerdLossRecord.objects.filter(herd=herd)
    loss_values = losses.aggregate(
        count=Count("id"), opening=Sum("opening_quantity"), lost=Sum("lost_quantity"),
    )
    opening = loss_values["opening"] or 0
    lost = loss_values["lost"] or 0
    loss_rate = Decimal(lost) / Decimal(opening) * Decimal("100") if opening else None
    sales = SaleRecord.objects.filter(target=herd)
    return {
        "growth": {
            "record_count": growth_values["count"],
            "total_weight": format(growth_values["total"] or Decimal("0"), ".2f"),
            "average_weight": format(growth_values["average"], ".2f") if growth_values["average"] is not None else None,
        },
        "cost": {"total_cost": format(cost_total, ".2f"), "by_category": cost_by_category,
                 "record_count": costs.count()},
        "loss": {
            "record_count": loss_values["count"], "opening_quantity": opening,
            "lost_quantity": lost, "loss_rate_percent": format(loss_rate, ".2f") if loss_rate is not None else None,
        },
        "sales": {
            "record_count": sales.count(),
            "revenue_total": format(derive_sales_revenue(sales), ".2f"),
        },
    }


def collect_chat_facts(sources, herd=None):
    """Run only fixed projections for allowlisted source names."""
    herds = Herd.objects.all()
    animals = Animal.objects.select_related("herd")
    animal_groups = AnimalGroup.objects.select_related("herd")
    pens = Pen.objects.select_related("herd", "animal_group", "animal")
    care = CareLog.objects.select_related("herd")
    feed = FeedRecord.objects.select_related("herd")
    medicine = MedicineRecord.objects.select_related("herd")
    schedules = VaccineSchedule.objects.select_related("target")
    vaccinations = VaccinationRecord.objects.select_related("schedule__target")
    growth = GrowthRecord.objects.select_related("target")
    reproduction = ReproductionRecord.objects.select_related("target")
    sales = SaleRecord.objects.select_related("target")
    if herd is not None:
        herds = herds.filter(pk=herd.pk)
        animals = animals.filter(herd=herd)
        animal_groups = animal_groups.filter(herd=herd)
        pens = pens.filter(Q(herd=herd) | Q(animal_group__herd=herd) | Q(animal__herd=herd))
        care = care.filter(herd=herd)
        feed = feed.filter(herd=herd)
        medicine = medicine.filter(herd=herd)
        schedules = schedules.filter(target=herd)
        vaccinations = vaccinations.filter(schedule__target=herd)
        growth = growth.filter(target=herd)
        reproduction = reproduction.filter(target=herd)
        sales = sales.filter(target=herd)
    facts = {}
    collectors = {
        "herds": lambda: _limited(herds,
            ("code", "name", "animal_type", "management_mode", "quantity", "status"), ("code",)),
        "animals": lambda: _limited(animals,
            ("code", "herd__code", "status"), ("code",)),
        "animal_groups": lambda: _limited(animal_groups,
            ("code", "name", "herd__code", "quantity", "status"), ("code",)),
        "pens": lambda: _limited(pens,
            ("code", "name", "location", "status", "herd__code", "animal_group__code", "animal__code"), ("code",)),
        "care": lambda: _limited(care,
            ("herd__code", "recorded_at", "activity", "notes"), ("-recorded_at", "pk")),
        "feed": lambda: _limited(feed,
            ("herd__code", "recorded_at", "feed_type", "quantity"), ("-recorded_at", "pk")),
        "medicine": lambda: _limited(medicine,
            ("herd__code", "recorded_at", "medicine", "dose"), ("-recorded_at", "pk")),
        "vaccines": lambda: (
            [{"record_type": "schedule", **row} for row in _limited(
                schedules,
                ("target__code", "vaccine", "scheduled_date", "status"), ("-scheduled_date", "pk"),
            )]
            + [{"record_type": "vaccination", **row} for row in _limited(
                vaccinations,
                ("schedule__target__code", "schedule__vaccine", "actual_date"), ("-actual_date", "pk"),
            )]
        ),
        "growth": lambda: _limited(growth,
            ("target__code", "measurement_date", "weight"), ("-measurement_date", "pk")),
        "reproduction": lambda: _limited(reproduction,
            ("target__code", "event_date", "event_type", "result"), ("-event_date", "pk")),
        "sales": lambda: _limited(sales,
            ("target__code", "sale_date", "quantity", "weight", "amount"), ("-sale_date", "pk")),
        "statistics": lambda: _collect_statistics(herd),
    }
    for source in sources:
        facts[source] = collectors[source]()
        if source == "care":
            for row in facts[source]:
                row["notes_truncated"] = len(row["notes"]) > MAX_NOTE_LENGTH
                row["notes"] = row["notes"][:MAX_NOTE_LENGTH]
    return facts


def _has_source_data(facts):
    for source, value in facts.items():
        if source == "statistics":
            if any((value["growth"]["record_count"], value["cost"]["record_count"],
                    value["loss"]["record_count"], value["sales"]["record_count"])):
                return True
        elif value:
            return True
    return False


def _format_record_value(value):
    labels = {
        "code": "mã", "name": "tên", "animal_type": "loại vật nuôi",
        "management_mode": "hình thức quản lý", "quantity": "số lượng",
        "status": "trạng thái", "herd__code": "mã đàn", "target__code": "mã đàn",
        "recorded_at": "thời điểm ghi nhận", "activity": "hoạt động", "notes": "ghi chú",
        "feed_type": "loại thức ăn", "medicine": "thuốc đã ghi nhận", "dose": "liều đã ghi nhận",
        "scheduled_date": "ngày dự kiến", "actual_date": "ngày thực hiện",
        "measurement_date": "ngày cân", "weight": "khối lượng", "event_date": "ngày sự kiện",
        "event_type": "loại sự kiện", "result": "kết quả ghi nhận", "sale_date": "ngày xuất bán",
        "amount": "giá trị ghi nhận", "location": "vị trí", "animal_group__code": "mã nhóm",
        "animal__code": "mã cá thể", "vaccine": "vaccine đã ghi nhận",
    }
    if isinstance(value, dict):
        return "; ".join(
            f"{labels.get(key, key.replace('__', ' ').replace('_', ' '))}: {_format_record_value(item)}"
            for key, item in value.items()
        )
    if isinstance(value, list):
        return " | ".join(_format_record_value(item) for item in value)
    return "chưa có" if value is None else str(value)


def _provider_failure_fallback(facts):
    """Show only the already collected facts if the model returns invalid output."""
    sections = []
    for source, value in facts.items():
        label = SOURCE_LABELS[source]
        if isinstance(value, list):
            records = [
                f"{index}. {_format_record_value(row)}"
                for index, row in enumerate(value, start=1)
            ]
        else:
            records = [_format_record_value(value)]
        if records:
            sections.append(f"{label}: " + " | ".join(records))
    details = "\n".join(sections)
    return f"AI chưa tạo được câu trả lời lúc này. Dữ liệu liên quan đã ghi nhận:\n{details}"


def answer_chat_question(user, question, history=()):
    if _is_explicitly_out_of_scope(f" {_normalize_question(question)} "):
        return {"answer": OUT_OF_SCOPE_ANSWER, "notice": CHAT_NOTICE, "source_count": 0}
    care_query_kind, care_query = _care_schedule_query_for_question(question, history)
    if care_query_kind == "mixed":
        return {"answer": CARE_SCHEDULE_MIXED_ANSWER, "notice": CHAT_NOTICE, "source_count": 0}
    if care_query_kind == "query":
        return _query_care_schedules(question, history, care_query)
    if care_query_kind == "clarify" or _is_care_schedule_request(question) or _is_care_schedule_follow_up(question, history):
        return {"answer": CARE_SCHEDULE_ANSWER, "notice": CHAT_NOTICE, "source_count": 0}
    if _is_greeting(question):
        return {
            "answer": "Chào bạn! Mình có thể tra cứu dữ liệu đàn, cá thể, chăm sóc, thức ăn, vaccine và các mục đã ghi nhận trong hệ thống.",
            "notice": CHAT_NOTICE,
            "source_count": 0,
        }

    sources = _resolve_chat_sources(question, history)
    if not sources:
        return {"answer": OUT_OF_SCOPE_ANSWER, "notice": CHAT_NOTICE, "source_count": 0}

    herd, herd_not_found = _resolve_chat_herd(question, history)
    if herd_not_found:
        return {"answer": HERD_NOT_FOUND_ANSWER, "notice": CHAT_NOTICE, "source_count": 0}

    if "vaccines" in sources and _is_vaccine_due_today_question(question):
        schedules = VaccineSchedule.objects.select_related("target").filter(
            scheduled_date=date.today(),
        ).order_by("target__code", "vaccine", "pk")
        if herd is not None:
            schedules = schedules.filter(target=herd)
        due_schedules = [
            schedule for schedule in schedules
            if schedule.status not in {
                VaccineSchedule.Status.COMPLETED,
                VaccineSchedule.Status.CANCELLED,
            }
        ]
        if due_schedules:
            entries = "; ".join(
                f"{schedule.target.code} — {schedule.target.name}: {schedule.vaccine}"
                for schedule in due_schedules
            )
            answer = f"Lịch vaccine ghi nhận đến hạn hôm nay ({date.today().isoformat()}): {entries}."
        else:
            answer = "Không có lịch vaccine nào được ghi nhận đến hạn hôm nay."
        return {
            "answer": answer,
            "notice": CHAT_NOTICE,
            "source_count": len(due_schedules),
        }

    # A count is an exact database aggregate, so it should not fail with an
    # empty or malformed provider response.
    if sources == ("herds",) and herd is None and _is_herd_count_question(question):
        herd_count = Herd.objects.count()
        answer = f"Hệ thống hiện ghi nhận {herd_count} đàn."
        return {"answer": answer, "notice": CHAT_NOTICE, "source_count": herd_count}

    # Listing the identity of a previously counted herd set is a fixed database
    # lookup; do not make a simple code/name answer depend on provider wording.
    if sources == ("herds",) and herd is None and _is_counted_herd_list_question(question):
        herds = list(Herd.objects.order_by("code").values("code", "name"))
        if herds:
            entries = "; ".join(f"{row['code']} — {row['name']}" for row in herds)
            answer = f"Hệ thống hiện ghi nhận {len(herds)} đàn: {entries}."
        else:
            answer = "Hệ thống chưa ghi nhận đàn nào."
        return {"answer": answer, "notice": CHAT_NOTICE, "source_count": len(herds)}

    if sources == ("herds",) and herd is not None and _is_herd_quantity_question(question):
        herd_data = Herd.objects.only("code", "name", "quantity").get(pk=herd.pk)
        answer = (
            f"Đàn {herd_data.code} ({herd_data.name}) có {herd_data.quantity} con "
            "theo số lượng đang ghi nhận trong hệ thống."
        )
        return {"answer": answer, "notice": CHAT_NOTICE, "source_count": 1}

    if sources == ("herds",) and herd is None and (
        _is_largest_herd_quantity_question(question) or _is_smallest_herd_quantity_question(question)
    ):
        is_smallest = _is_smallest_herd_quantity_question(question)
        extreme_label = "ít nhất" if is_smallest else "nhiều nhất"
        aggregate_key = "smallest" if is_smallest else "largest"
        aggregate = Min("quantity") if is_smallest else Max("quantity")
        quantity_extreme = Herd.objects.aggregate(**{aggregate_key: aggregate})[aggregate_key]
        if quantity_extreme is None:
            answer = "Hệ thống chưa ghi nhận đàn nào."
            source_count = 0
        else:
            extreme_herds = list(
                Herd.objects.filter(quantity=quantity_extreme).order_by("code").values("code", "name")
            )
            herd_names = "; ".join(f"{row['code']} — {row['name']}" for row in extreme_herds)
            answer = f"Đàn có số lượng ghi nhận {extreme_label}: {herd_names} ({quantity_extreme} con)."
            source_count = len(extreme_herds)
        return {"answer": answer, "notice": CHAT_NOTICE, "source_count": source_count}

    facts = collect_chat_facts(sources, herd=herd)
    source_count = sum(len(value) if isinstance(value, list) else
                       value["growth"]["record_count"] + value["cost"]["record_count"] +
                       value["loss"]["record_count"] + value["sales"]["record_count"]
                       for value in facts.values())
    if not _has_source_data(facts):
        labels = ", ".join(SOURCE_LABELS[source] for source in sources)
        return {
            "answer": f"Chưa có dữ liệu đã ghi nhận về {labels} trong hệ thống để trả lời câu hỏi này.",
            "notice": CHAT_NOTICE,
            "source_count": 0,
        }

    try:
        provider = get_configured_provider()
        result = AIOrchestrator(provider).run(
            user, build_chat_prompt(),
            {"question": question, "history": history, "sources": facts, "source_count": source_count},
        )
    except (AIConfigurationError, AIInvocationError) as exc:
        # Even when configuration or invocation fails, only these already
        # retrieved database facts are safe to present as a fallback.
        return {
            "answer": _provider_failure_fallback(facts),
            "notice": CHAT_NOTICE,
            "source_count": source_count,
        }
    answer = OUT_OF_SCOPE_ANSWER if _answer_requests_professional_advice(result.text) else result.text
    return {"answer": answer, "notice": CHAT_NOTICE, "source_count": source_count}
