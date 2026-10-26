"""Server-rendered management screens reusing the verified business layer."""
import logging
from functools import wraps
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import ValidationError as ApiValidationError

from apps.ai import growth_report, herd_summary, reminders
from apps.ai.providers import AIConfigurationError, AIError, get_configured_provider
from apps.ai.errors import PROVIDER_FAILURE, public_ai_error
from apps.ai.serializers import GrowthReportRequestSerializer, HerdSummaryRequestSerializer, ReminderRequestSerializer
from apps.users.permissions import ROLE_ACTIONS, RoleActionPermission
from apps.users.roles import get_user_role
from apps.vaccinations.serializers import get_alert_classification
from apps.care.models import CareSchedule
from apps.care.serializers import get_care_alert_classification
from .forms import AIFeatureForm, ResourceForm, add_validation_errors
from .resources import ALERT_LABELS, LABELS, RESOURCES
from .views import build_dashboard_context

logger = logging.getLogger(__name__)


def error_page(request, status=500):
    return render(request, "management/error.html", {"error_status": status}, status=status)


def guarded(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        from django.core.exceptions import PermissionDenied
        from django.http import Http404
        try:
            return view(request, *args, **kwargs)
        except Http404:
            return error_page(request, 404)
        except PermissionDenied:
            return error_page(request, 403)
        except Exception:
            logger.exception("Management screen failed path=%s", request.path)
            return error_page(request, 500)
    return wrapped


def allowed(request, resource, action):
    return RoleActionPermission().has_permission(
        request, SimpleNamespace(permission_resource=resource, permission_action=action)
    )


def navigation(request):
    role = get_user_role(request.user)
    items = [{"title": "Tổng quan", "url": reverse("dashboard"), "section": "dashboard"}]
    if role:
        items += [{"title": r.title, "url": r.url, "section": r.section}
                  for r in RESOURCES.values() if r.slug != "vaccination-records"
                  and "read" in ROLE_ACTIONS[r.viewset.permission_resource].get(role, set())]
        for slug, title in (("statistics", "Thống kê"), ("ai", "AI Assistant")):
            if "read" in ROLE_ACTIONS[slug].get(role, set()):
                items.append({"title": title, "url": reverse(f"ui-{slug}"), "section": slug})
    section = request.path.strip("/").split("/")[0]
    if section == "vaccination-records":
        section = "vaccines"
    return {"navigation": items if role else [], "nav_role": role, "active_section": section}


def display_cell(obj, name):
    if name == "alert_classification":
        raw = get_care_alert_classification(obj) if isinstance(obj, CareSchedule) else get_alert_classification(obj)
        return {"value": ALERT_LABELS.get(raw, "—"), "badge": True, "raw": raw or ""}
    value = getattr(obj, name)
    if name == "status" and obj._meta.get_field(name).choices:
        value = f"{obj.get_status_display()} ({value})"
    return {"value": value if value is not None and value != "" else "—", "badge": name == "status"}


def filter_controls(resource, request):
    controls = []
    for name in resource.viewset.exact_filter_fields:
        field = resource.model._meta.get_field(name)
        if field.is_relation:
            options = [(str(obj.pk), str(obj)) for obj in field.related_model.objects.all()]
        elif field.choices:
            options = [(str(key), label) for key, label in field.choices]
        else:
            options = [(value, value) for value in resource.model.objects.order_by(name).values_list(name, flat=True).distinct()]
        value = request.GET.get(name, "")
        if value and value not in [key for key, _ in options]:
            options.append((value, value))
        controls.append({"name": name, "label": LABELS[name], "options": options, "value": value})
    return controls


@login_required
@require_http_methods(["GET", "POST"])
@guarded
def resource_screen(request, slug, action="list", pk=None):
    resource = RESOURCES[slug]
    permission_action = {"list": "read", "detail": "read", "create": "create", "edit": "update", "delete": "delete"}[action]
    if not allowed(request, resource.viewset.permission_resource, permission_action):
        return error_page(request, 403)
    if request.method == "POST" and action in ("list", "detail"):
        return error_page(request, 405)
    context = {
        "resource": resource, "action": action,
        "can_create": allowed(request, resource.viewset.permission_resource, "create"),
        "can_edit": allowed(request, resource.viewset.permission_resource, "update"),
        "can_delete": allowed(request, resource.viewset.permission_resource, "delete"),
    }
    api_view = resource.viewset()
    api_view.request = SimpleNamespace(query_params=request.GET)
    api_view.format_kwarg = None
    queryset = api_view.get_queryset().select_related()
    if action == "list":
        context.update(filters=filter_controls(resource, request), search=request.GET.get("search", ""),
                       ordering=request.GET.get("ordering", ""),
                       sort_options=[(prefix + name, LABELS[name] + direction)
                                     for name in api_view.ordering_fields
                                     for prefix, direction in (("", " · tăng dần"), ("-", " · giảm dần"))])
        try:
            queryset = api_view.filter_queryset(queryset)
        except ApiValidationError:
            context["query_error"] = "Bộ lọc không hợp lệ. Vui lòng kiểm tra lại giá trị đã chọn."
            queryset = queryset.none()
        page = Paginator(queryset, 20).get_page(request.GET.get("page"))
        query = request.GET.copy()
        query.pop("page", None)
        context.update(page=page, page_query=query.urlencode(),
                       columns=[LABELS[name] for name in resource.columns],
                       rows=[{"pk": obj.pk, "object": obj, "cells": [display_cell(obj, name) for name in resource.columns]} for obj in page])
        return render(request, "management/list.html", context, status=400 if context.get("query_error") else 200)

    obj = get_object_or_404(queryset, pk=pk) if pk is not None else None
    context["object"] = obj
    if action == "detail":
        names = ["id"] + resource.fields
        if slug in ("vaccines", "care-schedules"):
            names += ["alert_classification"]
        context["details"] = [(LABELS[name], display_cell(obj, name)) for name in names]
        return render(request, "management/detail.html", context)
    if action == "delete":
        if request.method == "POST":
            try:
                with transaction.atomic():
                    obj.delete()
            except ProtectedError:
                context["delete_error"] = "Không thể xóa vì bản ghi đang được dữ liệu khác tham chiếu. Hãy kiểm tra các dữ liệu liên quan."
            else:
                messages.success(request, "Đã xóa bản ghi.")
                return redirect(resource.url)
        return render(request, "management/delete.html", context)

    form = ResourceForm(resource, request.POST if request.method == "POST" else None, instance=obj)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                saved = form.save()
        except DjangoValidationError as exc:
            add_validation_errors(form, exc)
        except ApiValidationError as exc:
            add_validation_errors(form, exc.detail)
        else:
            messages.success(request, "Đã lưu bản ghi thành công.")
            return redirect(f"{resource.url}{saved.pk}/")
    context["form"] = form
    return render(request, "management/form.html", context)


@login_required
@require_http_methods(["GET"])
@guarded
def statistics_screen(request):
    if not allowed(request, "statistics", "read"):
        return error_page(request, 403)
    context = build_dashboard_context(get_user_role(request.user))
    category_names = {"feed": "Thức ăn", "medicine": "Thuốc", "vaccine": "Vaccine", "care": "Chăm sóc", "other": "Khác"}
    context["cost_categories"] = [(category_names.get(key, key), value) for key, value in context["cost_statistics"]["by_category"].items()]
    return render(request, "management/statistics.html", context)


AI_FEATURES = {
    "reminders": ("Nhắc lịch", ReminderRequestSerializer, reminders.generate_reminders, "ai-reminders"),
    "herd_summary": ("Tóm tắt đàn", HerdSummaryRequestSerializer, herd_summary.generate_herd_summary, "ai-herd-summary"),
    "growth_report": ("Báo cáo tăng trưởng", GrowthReportRequestSerializer, growth_report.generate_growth_report, "ai-growth-report"),
}


def ai_cards(post=None):
    return [{"key": key, "title": spec[0], "endpoint": reverse(spec[3]),
             "form": AIFeatureForm(key, post if post is not None and post.get("feature") == key else None, prefix=key)}
            for key, spec in AI_FEATURES.items()]


@login_required
@require_http_methods(["GET", "POST"])
@guarded
def ai_screen(request):
    if not allowed(request, "ai", "read"):
        return error_page(request, 403)
    cards = ai_cards(request.POST if request.method == "POST" else None)
    context = {"ai_cards": cards}
    try:
        get_configured_provider()
    except AIConfigurationError:
        context["ai_unconfigured"] = True
    if request.method == "POST":
        key = request.POST.get("feature")
        if key not in AI_FEATURES:
            context["ai_error"] = "Chức năng không hợp lệ. Vui lòng chọn lại."
            return render(request, "management/ai.html", context, status=400)
        form = next(card["form"] for card in cards if card["key"] == key)
        spec = AI_FEATURES[key]
        if form.is_valid():
            serializer = spec[1](data=form.payload())
            try:
                serializer.is_valid(raise_exception=True)
            except ApiValidationError as exc:
                add_validation_errors(form, exc.detail)
            else:
                try:
                    result = spec[2](request.user, **serializer.validated_data)
                    context.update(ai_result=result, result_title=spec[0])
                    metric_labels = {
                        "record_count": "Số lần đo", "first_measurement_date": "Ngày đo đầu",
                        "last_measurement_date": "Ngày đo cuối", "first_weight": "Cân nặng đầu",
                        "last_weight": "Cân nặng cuối", "absolute_change": "Thay đổi cân nặng",
                        "percent_change": "Thay đổi (%)", "average_weight": "Cân nặng trung bình",
                    }
                    context["ai_metrics"] = [(metric_labels[name], value) for name, value in result.get("metrics", {}).items() if name in metric_labels]
                except AIError as exc:
                    logger.warning("AI screen generation failed feature=%s category=%s", key, exc.category.value)
                    context["ai_error"] = public_ai_error(exc).message
                except Exception as exc:
                    # No traceback: even unexpected exceptions can carry source data.
                    logger.warning("AI screen generation failed feature=%s category=%s", key, exc.__class__.__name__)
                    context["ai_error"] = PROVIDER_FAILURE.message
    return render(request, "management/ai.html", context)
