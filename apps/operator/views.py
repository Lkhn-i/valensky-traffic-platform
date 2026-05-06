from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.commerce.models import Order
from apps.curriculum.models import Course
from apps.events.models import AuditLog

from .services import (
    draft_course,
    draft_lesson,
    draft_module,
    enqueue_learner_access_link,
    get_content_readiness_snapshot,
    get_homework_review_queue,
    get_learner_support_snapshot,
    get_operator_dashboard_metrics,
    list_learner_support_items,
    publish_course,
    publish_lesson,
    publish_module,
    require_operator_permissions,
    review_homework_submission,
)

AUDIT_ACTION_LABELS = {
    "operator.course.publish": "Курс опубликован",
    "operator.course.draft": "Курс переведён в черновик",
    "operator.module.publish": "Модуль опубликован",
    "operator.module.draft": "Модуль переведён в черновик",
    "operator.lesson.publish": "Урок опубликован",
    "operator.lesson.draft": "Урок переведён в черновик",
    "operator.homework.review": "Домашка проверена",
    "operator.learner.resend_access_link": "Ссылка доступа отправлена повторно",
    "commerce.manual_mark_order_paid": "Заказ вручную отмечен оплаченным",
}

AUDIT_TARGET_LABELS = {
    "curriculum.Course": "Курс",
    "curriculum.Module": "Модуль",
    "curriculum.Lesson": "Урок",
    "homework.HomeworkSubmission": "Отправка домашки",
    "accounts.User": "Пользователь",
    "commerce.Order": "Заказ",
    "access_control.AccessGrant": "Доступ",
}


def _require_operator(request: HttpRequest, action: str) -> None:
    try:
        require_operator_permissions(user_id=request.user.id, action=action)
    except PermissionError as exc:
        raise PermissionDenied(str(exc)) from exc


@login_required
@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    _require_operator(request, "открыть операторскую панель")
    return render(
        request,
        "operator/dashboard.html",
        {"metrics": get_operator_dashboard_metrics()},
    )


@login_required
@require_GET
def learners(request: HttpRequest) -> HttpResponse:
    _require_operator(request, "смотреть учеников")
    query = request.GET.get("q", "")
    return render(
        request,
        "operator/learners.html",
        {
            "query": query,
            "learners": list_learner_support_items(query=query),
        },
    )


@login_required
@require_GET
def learner_detail(request: HttpRequest, user_id: int) -> HttpResponse:
    _require_operator(request, "смотреть карточку ученика")
    return render(
        request,
        "operator/learner_detail.html",
        {"snapshot": get_learner_support_snapshot(user_id=user_id)},
    )


@login_required
@require_POST
def resend_access_link(request: HttpRequest, user_id: int) -> HttpResponse:
    _require_operator(request, "отправить ссылку доступа ученику")
    reason = request.POST.get("reason", "Оператор запросил ссылку доступа для ученика")
    enqueue_learner_access_link(
        learner_user_id=user_id,
        actor_user_id=request.user.id,
        reason=reason,
    )
    messages.success(request, "Ссылка доступа поставлена в очередь отправки.")
    return redirect("operator:learner_detail", user_id=user_id)


@login_required
def content(request: HttpRequest) -> HttpResponse:
    _require_operator(request, "управлять контентом")
    if request.method == "POST":
        try:
            _handle_content_action(request)
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("operator:content")

    courses = (
        Course.objects.prefetch_related("modules__lessons")
        .all()
        .order_by("position", "title", "id")
    )
    _attach_content_readiness(courses)
    return render(request, "operator/content.html", {"courses": courses})


def _attach_content_readiness(courses: Iterable[Course]) -> None:
    for course in courses:
        course_model = cast(Any, course)
        course_model.readiness = get_content_readiness_snapshot(
            content_type="course",
            content_id=course.id,
        )
        for module in course.modules.all():
            module_model = cast(Any, module)
            module_model.readiness = get_content_readiness_snapshot(
                content_type="module",
                content_id=module.id,
            )
            for lesson in module.lessons.all():
                lesson_model = cast(Any, lesson)
                lesson_model.readiness = get_content_readiness_snapshot(
                    content_type="lesson",
                    content_id=lesson.id,
                )


def _handle_content_action(request: HttpRequest) -> None:
    entity_type = request.POST.get("entity_type", "")
    entity_id = int(request.POST.get("entity_id", "0"))
    status = request.POST.get("status", "")
    message = request.POST.get("message", "")
    actor_user_id = request.user.id

    if entity_type == "course" and status == "published":
        publish_course(course_id=entity_id, actor_user_id=actor_user_id, message=message)
    elif entity_type == "course" and status == "draft":
        draft_course(course_id=entity_id, actor_user_id=actor_user_id, message=message)
    elif entity_type == "module" and status == "published":
        publish_module(module_id=entity_id, actor_user_id=actor_user_id, message=message)
    elif entity_type == "module" and status == "draft":
        draft_module(module_id=entity_id, actor_user_id=actor_user_id, message=message)
    elif entity_type == "lesson" and status == "published":
        publish_lesson(lesson_id=entity_id, actor_user_id=actor_user_id, message=message)
    elif entity_type == "lesson" and status == "draft":
        draft_lesson(lesson_id=entity_id, actor_user_id=actor_user_id, message=message)
    else:
        raise ValueError("Неподдерживаемое действие с контентом.")
    messages.success(request, "Статус контента обновлён и записан в аудит.")


@login_required
@require_GET
def homework_queue(request: HttpRequest) -> HttpResponse:
    _require_operator(request, "смотреть очередь домашних заданий")
    return render(
        request,
        "operator/homework_queue.html",
        {"queue": get_homework_review_queue()},
    )


@login_required
@require_POST
def review_homework(request: HttpRequest, submission_id: int) -> HttpResponse:
    _require_operator(request, "проверять домашние задания")
    raw_score = request.POST.get("score", "").strip()
    score = None
    if raw_score:
        try:
            score = Decimal(raw_score)
        except InvalidOperation:
            messages.error(request, "Оценка должна быть числом.")
            return redirect("operator:homework_queue")

    review_homework_submission(
        submission_id=submission_id,
        reviewer_user_id=request.user.id,
        decision=request.POST.get("decision", ""),
        feedback=request.POST.get("feedback", ""),
        score=score,
    )
    messages.success(request, "Домашка проверена, событие записано в аудит.")
    return redirect("operator:homework_queue")


@login_required
@require_GET
def orders(request: HttpRequest) -> HttpResponse:
    _require_operator(request, "смотреть заказы")
    order_status = request.GET.get("status", "").strip()
    queryset = Order.objects.select_related("user", "course", "tariff", "access_grant").order_by(
        *Order._meta.ordering
    )
    if order_status:
        queryset = queryset.filter(status=order_status)
    return render(
        request,
        "operator/orders.html",
        {
            "orders": queryset[:100],
            "order_status": order_status,
            "order_status_options": Order.Status.choices,
        },
    )


@login_required
@require_GET
def audit(request: HttpRequest) -> HttpResponse:
    _require_operator(request, "смотреть журнал аудита")
    action = request.GET.get("action", "").strip()
    logs = AuditLog.objects.all().order_by(*AuditLog._meta.ordering)
    if action:
        logs = logs.filter(action__icontains=action)
    return render(
        request,
        "operator/audit.html",
        {
            "logs": _audit_log_rows(logs[:100]),
            "action": action,
            "audit_action_options": AUDIT_ACTION_LABELS.items(),
        },
    )


def _audit_log_rows(logs: Iterable[AuditLog]) -> list[dict[str, Any]]:
    return [
        {
            "occurred_at": log.occurred_at,
            "action_label": _audit_action_label(log.action),
            "actor_identifier": log.actor_identifier,
            "target_label": _audit_target_label(log.target_type, log.target_key),
            "result_label": log.get_result_display(),
            "message": log.message,
        }
        for log in logs
    ]


def _audit_action_label(action: str) -> str:
    return AUDIT_ACTION_LABELS.get(action, "Действие системы")


def _audit_target_label(target_type: str, target_key: str) -> str:
    if not target_type and not target_key:
        return "нет"
    target_label = AUDIT_TARGET_LABELS.get(target_type, "Объект")
    return f"{target_label} {target_key}" if target_key else target_label
