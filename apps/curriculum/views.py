from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from json import JSONDecodeError

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.access_control.models import Enrollment, Tariff
from apps.access_control.services import (
    AccessDecision,
    active_paid_grants_for_user_course,
    check_access,
    grant_preview_access,
)
from apps.accounts.services import get_or_create_lead_from_diagnostic
from apps.commerce.models import Order
from apps.events.services import ORMAnalyticsEventService
from apps.homework.services import (
    HomeworkGateDecision,
    check_lesson_homework_gate,
    find_previous_homework_blocker,
    homework_author_identifier,
    list_assignment_views_for_lesson,
    list_assignments_for_lesson,
    submit_text_answer,
)
from apps.integrations.services import enqueue_bot_outbox_from_notification
from apps.learning_state.models import ProgressRecord
from apps.learning_state.services import (
    LessonProgressSnapshot,
    complete_lesson,
    get_progress_for_lesson,
    list_progress_for_course,
    update_progress,
)
from apps.media_library.services import (
    ConsumedPlaybackTicketError,
    ExpiredPlaybackTicketError,
    PlaybackService,
    PlaybackSession,
    PlaybackState,
    PlaybackTicketNotFoundError,
)
from apps.notifications.services import TELEGRAM_CHANNEL, enqueue_lesson_completed_notification

from .models import Course, Lesson, Module

PUBLIC_PREVIEW_TTL_DAYS = 3
MAIN_MODULE_RELEASE_INTERVAL_DAYS = 7
MODULE_DOCUMENTS_METADATA_KEY = "accepted_module_documents"


@dataclass(frozen=True)
class LessonAccessView:
    lesson: Lesson
    decision: AccessDecision
    locked_reason: str
    progress: LessonProgressSnapshot
    status_label: str
    access_label: str
    ui_state: str
    ui_state_label: str
    progress_percent: int
    icon_key: str


@dataclass(frozen=True)
class ModuleAccessView:
    module: Module
    title: str
    display_title: str
    summary: str
    position: int
    display_index: str
    icon_key: str
    is_locked: bool
    locked_reason: str
    lessons: tuple[LessonAccessView, ...]
    completed_count: int
    total_count: int
    progress_percent: int
    homework_count: int
    average_score_label: str
    status_label: str
    is_completed: bool
    next_lesson: Lesson | None
    next_step_label: str
    documents_accepted: bool
    can_accept_documents: bool
    documents_required: bool


@dataclass(frozen=True)
class DashboardHomeworkView:
    title: str
    lesson: Lesson
    status_label: str
    due_label: str


@dataclass(frozen=True)
class DashboardActivityView:
    title: str
    detail: str


@dataclass(frozen=True)
class CourseDashboardView:
    course: Course
    enrollment_status: str
    tariff_label: str
    completed_count: int
    total_count: int
    progress_percent: int
    completed_module_count: int
    total_module_count: int
    homework_completed_count: int
    homework_total_count: int
    next_lesson: Lesson | None
    next_homework: DashboardHomeworkView | None
    recent_actions: tuple[DashboardActivityView, ...]
    available_tariffs: tuple[Tariff, ...]
    latest_order: Order | None
    access_state_label: str
    access_state_hint: str
    payment_state_label: str
    access_mode_label: str
    access_mode_hint: str
    lesson0: Lesson | None
    workshop_module: Module | None


def _locked_reason(decision: AccessDecision) -> str:
    if decision.allowed:
        return ""
    if decision.reason == "course_unpublished":
        return "Курс пока в черновике и недоступен ученикам."
    if decision.reason == "module_unpublished":
        return "Модуль пока в черновике и недоступен ученикам."
    if decision.reason == "lesson_unpublished":
        return "Урок пока в черновике и недоступен ученикам."
    if decision.reason == "homework_stop_lesson":
        return "Следующий урок откроется после принятой домашки в предыдущем уроке."
    if decision.reason == "previous_lesson_required":
        return "Сначала завершите предыдущий доступный урок. Перепрыгивать уроки нельзя."
    if decision.reason == "previous_module_documents_required":
        return "Перед следующим модулем нужно подтвердить документы по предыдущему модулю."
    if decision.reason == "module_drip_locked":
        return "Модуль открывается по расписанию курса, спустя время после старта доступа."
    if decision.reason == "not_in_tariff_entitlements":
        return "Этот урок не входит в текущий тариф."
    if decision.reason == "missing_paid_access_grant":
        return "Откроется после регистрации и оплаты обучения."
    return "Доступ к уроку сейчас закрыт."


def _lesson_progress_percent(progress: LessonProgressSnapshot) -> int:
    if progress.is_completed:
        return 100
    raw_percent = progress.metadata.get("percent", progress.metadata.get("watch_percent", 0))
    try:
        percent = int(raw_percent)
    except (TypeError, ValueError):
        percent = 0
    if percent > 0:
        return max(0, min(percent, 99))
    if progress.status == ProgressRecord.Status.IN_PROGRESS:
        return 70
    if progress.status == ProgressRecord.Status.OPENED:
        return 25
    return 0


def _lesson_ui_state(*, decision: AccessDecision, progress: LessonProgressSnapshot) -> str:
    if progress.is_completed:
        return "completed"
    if decision.allowed and progress.status in {
        ProgressRecord.Status.OPENED,
        ProgressRecord.Status.IN_PROGRESS,
    }:
        return "in_progress"
    if decision.allowed:
        return "available"
    if decision.reason == "module_drip_locked":
        return "time_locked"
    if decision.reason == "homework_stop_lesson":
        return "homework_locked"
    if decision.reason == "previous_lesson_required":
        return "previous_locked"
    if decision.reason == "previous_module_documents_required":
        return "documents_locked"
    if decision.reason == "not_in_tariff_entitlements":
        return "tariff_locked"
    return "locked"


def _lesson_ui_state_label(ui_state: str) -> str:
    labels = {
        "completed": "Завершён",
        "in_progress": "В процессе",
        "available": "Доступен",
        "time_locked": "Откроется по времени",
        "homework_locked": "ДЗ не принято",
        "previous_locked": "Предыдущий урок не пройден",
        "documents_locked": "Документы не подтверждены",
        "tariff_locked": "Не входит в тариф",
        "locked": "Закрыт",
    }
    return labels.get(ui_state, "Закрыт")


def _lesson_icon_key(lesson: Lesson, *, decision: AccessDecision) -> str:
    if not decision.allowed:
        if decision.reason == "module_drip_locked":
            return "clock"
        if decision.reason == "homework_stop_lesson":
            return "document"
        return "lock"
    icons = ("target", "magnet", "team", "rocket", "clock", "document", "star")
    return icons[(lesson.position - 1) % len(icons)]


def _module_display_title(module: Module) -> str:
    display_index = _module_display_index(module)
    prefixes = (
        f"Модуль {display_index}. ",
        f"Модуль {module.position}. ",
        f"Урок {display_index}. ",
    )
    for prefix in prefixes:
        if module.title.startswith(prefix):
            return module.title[len(prefix) :]
    if module.slug == "start":
        return "Вход в курс"
    if module.slug == "workshop":
        return "Быстрый запуск трафика"
    return module.title


def _module_homework_count(*, user_id: int, module: Module) -> int:
    author_identifier = homework_author_identifier(user_id)
    total_count = 0
    for lesson in module.lessons.all():
        total_count += len(
            list_assignment_views_for_lesson(
                lesson_id=lesson.id,
                author_identifier=author_identifier,
            )
        )
    return total_count


def _module_average_score_label(*, completed_count: int, total_count: int) -> str:
    if total_count <= 0 or completed_count <= 0:
        return "0%"
    return f"{max(70, min(95, round((completed_count / total_count) * 100)))}%"


def _module_status_label(module_view_state: str) -> str:
    labels = {
        "completed": "Завершён",
        "locked": "Заблокирован",
        "in_progress": "В процессе",
    }
    return labels.get(module_view_state, "В процессе")


def _lesson_access_view(*, user_id: int, lesson: Lesson) -> LessonAccessView:
    decision = _effective_lesson_access_decision(user_id=user_id, lesson=lesson)
    progress = get_progress_for_lesson(user_id, lesson.id)
    ui_state = _lesson_ui_state(decision=decision, progress=progress)
    return LessonAccessView(
        lesson=lesson,
        decision=decision,
        locked_reason=_locked_reason(decision),
        progress=progress,
        status_label=_progress_status_label(progress),
        access_label=_access_label(decision),
        ui_state=ui_state,
        ui_state_label=_lesson_ui_state_label(ui_state),
        progress_percent=_lesson_progress_percent(progress),
        icon_key=_lesson_icon_key(lesson, decision=decision),
    )


def _module_access_view(*, user_id: int, module: Module) -> ModuleAccessView:
    lesson_views = tuple(
        _lesson_access_view(user_id=user_id, lesson=lesson)
        for lesson in module.lessons.all()
    )
    completed_count = sum(lesson_view.progress.is_completed for lesson_view in lesson_views)
    is_locked = not any(lesson_view.decision.allowed for lesson_view in lesson_views)
    first_locked_reason = next(
        (lesson_view.locked_reason for lesson_view in lesson_views if lesson_view.locked_reason),
        "",
    )
    documents_required = _module_documents_required(user_id=user_id, module=module)
    documents_accepted = _module_documents_accepted(user_id=user_id, module=module)
    homework_count = _module_homework_count(user_id=user_id, module=module)
    is_completed = bool(lesson_views) and completed_count == len(lesson_views)
    module_state = "completed" if is_completed else "locked" if is_locked else "in_progress"
    return ModuleAccessView(
        module=module,
        title=module.title,
        display_title=_module_display_title(module),
        summary=module.summary,
        position=module.position,
        display_index=_module_display_index(module),
        icon_key=_module_icon_key(module),
        is_locked=is_locked,
        locked_reason=first_locked_reason if is_locked else "",
        lessons=lesson_views,
        completed_count=completed_count,
        total_count=len(lesson_views),
        progress_percent=_dashboard_percent(
            completed_count=completed_count,
            total_count=len(lesson_views),
        ),
        homework_count=homework_count,
        average_score_label=_module_average_score_label(
            completed_count=completed_count,
            total_count=len(lesson_views),
        ),
        status_label=_module_status_label(module_state),
        is_completed=is_completed,
        next_lesson=_module_next_lesson(lesson_views=lesson_views),
        next_step_label=_module_next_step_label(
            is_locked=is_locked,
            first_locked_reason=first_locked_reason,
            completed_count=completed_count,
            total_count=len(lesson_views),
            lesson_views=lesson_views,
        ),
        documents_accepted=documents_accepted,
        can_accept_documents=(
            documents_required
            and not documents_accepted
            and len(lesson_views) > 0
            and completed_count == len(lesson_views)
        ),
        documents_required=documents_required,
    )


def _module_display_index(module: Module) -> str:
    if module.position == 0:
        return "0"
    if module.slug == "workshop" or module.position == 1:
        return "W"
    return str(module.position - 1)


def _module_icon_key(module: Module) -> str:
    if module.position == 0:
        return "video"
    if module.slug == "workshop" or module.position == 1:
        return "cup"
    icon_by_index = {
        "1": "target",
        "2": "funnel",
        "3": "magnet",
        "4": "mail",
        "5": "money",
        "6": "chart",
        "7": "gear",
    }
    return icon_by_index.get(_module_display_index(module), "module")


def _module_next_lesson(*, lesson_views: tuple[LessonAccessView, ...]) -> Lesson | None:
    for lesson_view in lesson_views:
        if lesson_view.decision.allowed and not lesson_view.progress.is_completed:
            return lesson_view.lesson
    return None


def _module_primary_lesson_view(
    *, lesson_views: tuple[LessonAccessView, ...]
) -> LessonAccessView | None:
    for lesson_view in lesson_views:
        if lesson_view.decision.allowed and not lesson_view.progress.is_completed:
            return lesson_view
    for lesson_view in lesson_views:
        if lesson_view.decision.allowed:
            return lesson_view
    if lesson_views:
        return lesson_views[0]
    return None


def _lesson_display_code(lesson: Lesson) -> str:
    if lesson.module.position == 0:
        return "0"
    display_index = _module_display_index(lesson.module)
    if display_index == "W":
        return f"W.{lesson.position + 1}"
    return f"{display_index}.{lesson.position + 1}"


def _adjacent_module_lesson(*, lesson: Lesson, offset: int) -> Lesson | None:
    module_lessons = tuple(
        Lesson.objects.filter(
            module_id=lesson.module_id,
            publication_status=Lesson.PublicationStatus.PUBLISHED,
        ).order_by("position", "id")
    )
    current_index = next(
        (
            index
            for index, module_lesson in enumerate(module_lessons)
            if module_lesson.id == lesson.id
        ),
        -1,
    )
    target_index = current_index + offset
    if current_index < 0 or target_index < 0 or target_index >= len(module_lessons):
        return None
    return module_lessons[target_index]


def _course_workshop_module(*, course_id: int) -> Module | None:
    return (
        Module.objects.filter(course_id=course_id, slug="workshop")
        .order_by("position", "id")
        .first()
    )


def _module_next_step_label(
    *,
    is_locked: bool,
    first_locked_reason: str,
    completed_count: int,
    total_count: int,
    lesson_views: tuple[LessonAccessView, ...],
) -> str:
    if is_locked:
        return first_locked_reason or "Доступ к модулю закрыт."
    if total_count > 0 and completed_count == total_count:
        return "Курс готов. Можно двигаться дальше"
    next_lesson = _module_next_lesson(lesson_views=lesson_views)
    if next_lesson is not None:
        return next_lesson.title
    return "Открыть модуль и продолжить обучение"


def _course_map_sort_key(module_view: ModuleAccessView) -> tuple[int, int, int]:
    if module_view.module.position == 0:
        return (0, 0, module_view.module.id)
    if module_view.module.slug == "workshop" or module_view.module.position == 1:
        return (2, module_view.module.position, module_view.module.id)
    return (1, module_view.module.position, module_view.module.id)


def _progress_status_label(progress: LessonProgressSnapshot) -> str:
    if progress.status == ProgressRecord.Status.COMPLETED:
        return "Завершено"
    if progress.status in {
        ProgressRecord.Status.OPENED,
        ProgressRecord.Status.IN_PROGRESS,
    }:
        return "В процессе"
    return "Не начато"


def _access_label(decision: AccessDecision) -> str:
    if decision.grant_type == "paid":
        return "Тариф"
    if decision.grant_type == "preview":
        return "Пробный доступ"
    if decision.reason == "staff_role":
        return "Команда"
    if decision.reason == "not_in_tariff_entitlements":
        return "Не в тарифе"
    return "Закрыт"


def _active_enrollment(*, user_id: int, course_id: int) -> Enrollment | None:
    return (
        Enrollment.objects.select_related("course", "tariff")
        .filter(user_id=user_id, course_id=course_id)
        .order_by("-started_at", "-id")
        .first()
    )


def _active_tariffs(*, course_id: int) -> tuple[Tariff, ...]:
    return tuple(
        Tariff.objects.filter(course_id=course_id, is_active=True).order_by(
            *Tariff._meta.ordering
        )
    )


def _published_course_lessons(*, course_id: int) -> tuple[Lesson, ...]:
    lessons = tuple(
        Lesson.objects.select_related("module", "module__course")
        .filter(
            module__course_id=course_id,
            module__publication_status=Module.PublicationStatus.PUBLISHED,
            publication_status=Lesson.PublicationStatus.PUBLISHED,
        )
        .order_by("module__position", "position", "id")
    )
    return tuple(sorted(lessons, key=_course_sequence_lesson_sort_key))


def _course_sequence_lesson_sort_key(lesson: Lesson) -> tuple[int, int, int, int]:
    if lesson.module.position == 0:
        return (0, 0, lesson.position, lesson.id)
    if lesson.module.slug == "workshop" or lesson.module.position == 1:
        return (2, lesson.module.position, lesson.position, lesson.id)
    return (1, lesson.module.position, lesson.position, lesson.id)


def _base_lesson_access_decision(*, user_id: int, lesson: Lesson) -> AccessDecision:
    return check_access(user_id=user_id, lesson_id=lesson.id)


def _base_lesson_is_accessible(*, user_id: int, lesson: Lesson) -> bool:
    return _base_lesson_access_decision(user_id=user_id, lesson=lesson).allowed


def _paid_access_exists(*, user_id: int, course_id: int) -> bool:
    return active_paid_grants_for_user_course(user_id=user_id, course_id=course_id).exists()


def _module_release_delay_days(module: Module) -> int:
    if module.position <= 1:
        return 0
    return max(module.position - 2, 0) * MAIN_MODULE_RELEASE_INTERVAL_DAYS


def _module_release_locked_decision(*, user_id: int, module: Module) -> AccessDecision | None:
    if not _paid_access_exists(user_id=user_id, course_id=module.course_id):
        return None
    release_delay_days = _module_release_delay_days(module)
    if release_delay_days <= 0:
        return None
    enrollment = _active_enrollment(user_id=user_id, course_id=module.course_id)
    if enrollment is None:
        return None
    release_at = enrollment.started_at + timedelta(days=release_delay_days)
    if release_at <= timezone.now():
        return None
    return AccessDecision(allowed=False, reason="module_drip_locked")


def _previous_accessible_lesson(*, user_id: int, lesson: Lesson) -> Lesson | None:
    previous_lesson: Lesson | None = None
    for candidate in _published_course_lessons(course_id=lesson.module.course_id):
        if candidate.id == lesson.id:
            return previous_lesson
        if _base_lesson_is_accessible(user_id=user_id, lesson=candidate):
            previous_lesson = candidate
    return previous_lesson


def _previous_accessible_module(*, user_id: int, module: Module) -> Module | None:
    previous_module: Module | None = None
    modules = (
        Module.objects.prefetch_related("lessons")
        .filter(
            course_id=module.course_id,
            publication_status=Module.PublicationStatus.PUBLISHED,
        )
        .order_by("position", "id")
    )
    for candidate_module in modules:
        if candidate_module.id == module.id:
            return previous_module
        has_base_access = any(
            _base_lesson_is_accessible(user_id=user_id, lesson=lesson)
            for lesson in candidate_module.lessons.all()
        )
        if has_base_access:
            previous_module = candidate_module
    return previous_module


def _progress_is_completed(*, user_id: int, lesson: Lesson) -> bool:
    return get_progress_for_lesson(user_id, lesson.id).is_completed


def _is_last_published_lesson_in_module(lesson: Lesson) -> bool:
    return not Lesson.objects.filter(
        module_id=lesson.module_id,
        publication_status=Lesson.PublicationStatus.PUBLISHED,
        position__gt=lesson.position,
    ).exists()


def _module_documents_required(*, user_id: int, module: Module) -> bool:
    if module.slug == "workshop":
        return False
    if not _paid_access_exists(user_id=user_id, course_id=module.course_id):
        return False
    return any(
        _base_lesson_is_accessible(user_id=user_id, lesson=lesson)
        for lesson in module.lessons.all()
    )


def _accepted_module_document_slugs(*, user_id: int, course_id: int) -> set[str]:
    enrollment = _active_enrollment(user_id=user_id, course_id=course_id)
    if enrollment is None:
        return set()
    accepted_documents = enrollment.metadata.get(MODULE_DOCUMENTS_METADATA_KEY, {})
    if not isinstance(accepted_documents, dict):
        return set()
    return {str(module_slug) for module_slug in accepted_documents}


def _module_documents_accepted(*, user_id: int, module: Module) -> bool:
    if not _module_documents_required(user_id=user_id, module=module):
        return True
    return module.slug in _accepted_module_document_slugs(
        user_id=user_id,
        course_id=module.course_id,
    )


def _mark_module_documents_accepted(*, user_id: int, module: Module) -> None:
    enrollment = _active_enrollment(user_id=user_id, course_id=module.course_id)
    if enrollment is None:
        return
    metadata = dict(enrollment.metadata or {})
    accepted_documents = metadata.get(MODULE_DOCUMENTS_METADATA_KEY, {})
    if not isinstance(accepted_documents, dict):
        accepted_documents = {}
    accepted_documents[module.slug] = timezone.now().isoformat()
    metadata[MODULE_DOCUMENTS_METADATA_KEY] = accepted_documents
    Enrollment.objects.filter(id=enrollment.id).update(metadata=metadata)


def _effective_lesson_access_decision(*, user_id: int, lesson: Lesson) -> AccessDecision:
    base_decision = _base_lesson_access_decision(user_id=user_id, lesson=lesson)
    if not base_decision.allowed or base_decision.reason == "staff_role":
        return base_decision

    homework_gate = find_previous_homework_blocker(
        lesson=lesson,
        author_identifier=homework_author_identifier(user_id),
    )
    if not homework_gate.allowed:
        return AccessDecision(
            allowed=False,
            reason="homework_stop_lesson",
            grant_id=base_decision.grant_id,
            grant_type=base_decision.grant_type,
        )

    previous_lesson = _previous_accessible_lesson(user_id=user_id, lesson=lesson)
    if previous_lesson is not None and not _progress_is_completed(
        user_id=user_id,
        lesson=previous_lesson,
    ):
        return AccessDecision(
            allowed=False,
            reason="previous_lesson_required",
            grant_id=base_decision.grant_id,
            grant_type=base_decision.grant_type,
        )

    if lesson.module.slug != "workshop":
        previous_module = _previous_accessible_module(user_id=user_id, module=lesson.module)
        if previous_module is not None and not _module_documents_accepted(
            user_id=user_id,
            module=previous_module,
        ):
            return AccessDecision(
                allowed=False,
                reason="previous_module_documents_required",
                grant_id=base_decision.grant_id,
                grant_type=base_decision.grant_type,
            )

    drip_decision = _module_release_locked_decision(user_id=user_id, module=lesson.module)
    if drip_decision is not None:
        return AccessDecision(
            allowed=False,
            reason=drip_decision.reason,
            grant_id=base_decision.grant_id,
            grant_type=base_decision.grant_type,
        )

    return base_decision


def _lesson0_for_course(course: Course) -> Lesson:
    return Lesson.objects.select_related("module", "module__course").get(
        module__course=course,
        module__position=0,
        position=0,
    )


def _public_preview_session_id(request: HttpRequest, *, course_slug: str) -> str:
    explicit_session_id = (
        request.GET.get("session_id")
        or request.GET.get("diagnostic_session_id")
        or request.GET.get("lead_id")
        or ""
    ).strip()
    if explicit_session_id:
        return explicit_session_id[:128]
    if not request.session.session_key:
        request.session.create()
    return f"public-preview:{course_slug}:{request.session.session_key}"


def _login_public_preview_lead(request: HttpRequest, *, course: Course) -> None:
    lesson0 = _lesson0_for_course(course)
    external_session_id = _public_preview_session_id(request, course_slug=course.slug)
    lead_profile, created_lead = get_or_create_lead_from_diagnostic(
        external_session_id=external_session_id,
        diagnostic_segment=(request.GET.get("segment") or "public-preview")[:128],
        source="diagnostic_site",
    )
    preview_grant = grant_preview_access(
        lead_profile_id=lead_profile.id,
        course_id=course.id,
        lesson_id=lesson0.id,
        expires_at=timezone.now() + timedelta(days=PUBLIC_PREVIEW_TTL_DAYS),
    )
    login(
        request,
        lead_profile.user,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    ORMAnalyticsEventService().record_event(
        name="public_preview_opened",
        source_app="curriculum",
        actor_identifier=str(lead_profile.user_id),
        session_identifier=external_session_id,
        object_type="course",
        object_key=str(course.id),
        properties={
            "course_slug": course.slug,
            "lesson_id": lesson0.id,
            "preview_grant_id": preview_grant.id,
            "created_lead": created_lead,
        },
    )


def _latest_order(*, user_id: int, course_id: int) -> Order | None:
    return (
        Order.objects.select_related("tariff", "course")
        .filter(user_id=user_id, course_id=course_id)
        .order_by(*Order._meta.ordering)
        .first()
    )


def _access_state_label(enrollment: Enrollment) -> str:
    if enrollment.status == Enrollment.Status.ACTIVE:
        return "Доступ открыт"
    if enrollment.status == Enrollment.Status.PREVIEW:
        return "Пробный доступ"
    return "Доступ ограничен"


def _access_state_hint(*, enrollment: Enrollment, latest_order: Order | None) -> str:
    if enrollment.status == Enrollment.Status.ACTIVE:
        return "Платные модули открыты в рамках выбранного тарифа."
    if latest_order is not None and latest_order.status in {
        Order.Status.CREATED,
        Order.Status.PENDING,
    }:
        return "Заказ подготовлен, но платёжный провайдер пока работает как заглушка."
    return "Урок 0 открыт, остальные модули откроются после регистрации и оплаты."


def _access_mode_label(enrollment: Enrollment | None) -> str:
    if enrollment is None:
        return "LESSON0-ONLY"
    if enrollment.status == Enrollment.Status.PREVIEW:
        return "LESSON0-ONLY"
    if enrollment.tariff is None:
        return "FULL COURSE"
    if enrollment.tariff.code == Tariff.Code.WORKSHOP:
        return "WORKSHOP"
    if enrollment.tariff.code in {Tariff.Code.MENTOR, Tariff.Code.VIP}:
        return "FULL WITH HOMEWORK"
    return "FULL COURSE"


def _access_mode_hint(enrollment: Enrollment | None) -> str:
    if enrollment is None or enrollment.status == Enrollment.Status.PREVIEW:
        return "Открыт только Урок 0 после опроса."
    if enrollment.tariff and enrollment.tariff.code == Tariff.Code.WORKSHOP:
        return "Открыта отдельная ветка воркшопа и подготовительные материалы."
    if enrollment.tariff and enrollment.tariff.code in {Tariff.Code.MENTOR, Tariff.Code.VIP}:
        return "Открыт полный курс, домашние задания и проверка куратором."
    return "Открыт полный курс без проверки домашних заданий."


def _payment_state_label(latest_order: Order | None) -> str:
    if latest_order is None:
        return "Заказ не создан"
    labels = {
        Order.Status.CREATED: "Заказ подготовлен",
        Order.Status.PENDING: "Ожидает подтверждения",
        Order.Status.PAID: "Оплачено",
        Order.Status.FAILED: "Оплата не прошла",
        Order.Status.REFUNDED: "Возврат",
        Order.Status.DISPUTED: "На проверке",
    }
    return labels.get(latest_order.status, latest_order.status)


def _queue_lesson_completed_message(
    *,
    user_id: int,
    progress_id: int,
    course_slug: str,
    lesson_id: int,
    lesson_slug: str,
) -> None:
    notification_job = enqueue_lesson_completed_notification(
        user_id=user_id,
        course_slug=course_slug,
        lesson_slug=lesson_slug,
        channel=TELEGRAM_CHANNEL,
        payload={
            "progress_id": progress_id,
            "lesson_id": lesson_id,
        },
        dedupe_key=f"lesson-completed:{progress_id}",
    )
    enqueue_bot_outbox_from_notification(
        notification_job_id=notification_job.id,
        template_key=notification_job.template_key,
        idempotency_key=f"bot:lesson-completed:{progress_id}",
        event_type="lesson.completed",
        user_id=user_id,
        payload={
            "progress_id": progress_id,
            "course_slug": course_slug,
            "lesson_id": lesson_id,
            "lesson_slug": lesson_slug,
        },
    )


def _tariff_label(enrollment: Enrollment | None) -> str:
    if enrollment is None:
        return "Нет доступа"
    if enrollment.tariff is not None:
        return enrollment.tariff.title
    if enrollment.status == Enrollment.Status.PREVIEW:
        return "Пробный доступ"
    return "Без тарифа"


def _next_accessible_lesson(*, user_id: int, course_id: int) -> Lesson | None:
    lessons = _published_course_lessons(course_id=course_id)
    progress_by_lesson_id = {
        snapshot.lesson_id: snapshot
        for snapshot in list_progress_for_course(user_id=user_id, course_id=course_id)
    }
    for lesson in lessons:
        if not _effective_lesson_access_decision(user_id=user_id, lesson=lesson).allowed:
            continue
        homework_gate = find_previous_homework_blocker(
            lesson=lesson,
            author_identifier=homework_author_identifier(user_id),
        )
        if not homework_gate.allowed:
            continue
        progress = progress_by_lesson_id.get(lesson.id)
        if progress is None or not progress.is_completed:
            return lesson
    return None


def _course_base_access_lesson_ids(*, user_id: int, course_id: int) -> set[int]:
    return {
        lesson.id
        for lesson in _published_course_lessons(course_id=course_id)
        if _base_lesson_is_accessible(user_id=user_id, lesson=lesson)
    }


def _course_progress_counts(*, user_id: int, course_id: int) -> tuple[int, int, int]:
    progress = list_progress_for_course(user_id=user_id, course_id=course_id)
    base_access_lesson_ids = _course_base_access_lesson_ids(
        user_id=user_id,
        course_id=course_id,
    )
    completed_count = sum(
        snapshot.is_completed
        for snapshot in progress
        if snapshot.lesson_id in base_access_lesson_ids
    )
    total_count = len(base_access_lesson_ids)
    return (
        completed_count,
        total_count,
        _dashboard_percent(completed_count=completed_count, total_count=total_count),
    )


def _dashboard_percent(*, completed_count: int, total_count: int) -> int:
    if total_count <= 0:
        return 0
    return round((completed_count / total_count) * 100)


def _dashboard_module_counts(
    *,
    progress: list[LessonProgressSnapshot],
    base_access_lesson_ids: set[int],
) -> tuple[int, int]:
    lessons_by_module: dict[int, list[LessonProgressSnapshot]] = {}
    for snapshot in progress:
        if snapshot.lesson_id not in base_access_lesson_ids:
            continue
        lessons_by_module.setdefault(snapshot.module_id, []).append(snapshot)
    completed_modules = sum(
        all(snapshot.is_completed for snapshot in module_progress)
        for module_progress in lessons_by_module.values()
        if module_progress
    )
    return completed_modules, len(lessons_by_module)


def _dashboard_due_label(due_at: object | None) -> str:
    if due_at is None:
        return "Срок сдачи: по расписанию урока"
    return f"Срок сдачи: {timezone.localtime(due_at).strftime('%d.%m, %H:%M')}"


def _dashboard_homework_snapshot(
    *,
    user_id: int,
    course_id: int,
) -> tuple[int, int, DashboardHomeworkView | None]:
    author_identifier = homework_author_identifier(user_id)
    submitted_statuses = {"submitted", "reviewed"}
    completed_count = 0
    total_count = 0
    next_homework: DashboardHomeworkView | None = None

    for lesson in _published_course_lessons(course_id=course_id):
        if not _base_lesson_is_accessible(user_id=user_id, lesson=lesson):
            continue
        assignment_views = list_assignment_views_for_lesson(
            lesson_id=lesson.id,
            author_identifier=author_identifier,
        )
        if not assignment_views:
            continue
        assignments_by_slug = {
            assignment.slug: assignment
            for assignment in list_assignments_for_lesson(lesson_id=lesson.id)
        }
        for assignment_view in assignment_views:
            total_count += 1
            if assignment_view.status_code in submitted_statuses:
                completed_count += 1
            if next_homework is None and assignment_view.status_code not in submitted_statuses:
                assignment = assignments_by_slug.get(assignment_view.slug)
                next_homework = DashboardHomeworkView(
                    title=assignment_view.title,
                    lesson=lesson,
                    status_label=assignment_view.status_label,
                    due_label=_dashboard_due_label(assignment.due_at if assignment else None),
                )

    return completed_count, total_count, next_homework


def _dashboard_recent_actions(
    *,
    progress: list[LessonProgressSnapshot],
    lessons: tuple[Lesson, ...],
    next_lesson: Lesson | None,
    next_homework: DashboardHomeworkView | None,
) -> tuple[DashboardActivityView, ...]:
    lessons_by_id = {lesson.id: lesson for lesson in lessons}
    actions: list[DashboardActivityView] = []
    opened_snapshots = sorted(
        (snapshot for snapshot in progress if snapshot.last_opened_at is not None),
        key=lambda snapshot: snapshot.last_opened_at,
        reverse=True,
    )
    if opened_snapshots:
        lesson = lessons_by_id.get(opened_snapshots[0].lesson_id)
        if lesson is not None:
            actions.append(
                DashboardActivityView(
                    title="Смотрели",
                    detail=f"{lesson.module.title}: {lesson.title}",
                )
            )

    completed_snapshots = sorted(
        (snapshot for snapshot in progress if snapshot.completed_at is not None),
        key=lambda snapshot: snapshot.completed_at,
        reverse=True,
    )
    if completed_snapshots:
        lesson = lessons_by_id.get(completed_snapshots[0].lesson_id)
        if lesson is not None:
            actions.append(
                DashboardActivityView(
                    title="Завершили урок",
                    detail=f"{lesson.module.title}: {lesson.title}",
                )
            )

    if next_homework is not None:
        actions.append(
            DashboardActivityView(
                title="Домашка",
                detail=f"{next_homework.title}: {next_homework.status_label}",
            )
        )

    if next_lesson is not None:
        actions.append(
            DashboardActivityView(
                title="Следующий шаг",
                detail=f"{next_lesson.module.title}: {next_lesson.title}",
            )
        )

    if not actions:
        actions.append(
            DashboardActivityView(
                title="Открыт кабинет",
                detail="Продолжите обучение с доступной карты курса.",
            )
        )
    return tuple(actions[:3])


def _course_dashboard_view(*, user_id: int, enrollment: Enrollment) -> CourseDashboardView:
    progress = list_progress_for_course(user_id=user_id, course_id=enrollment.course_id)
    lessons = _published_course_lessons(course_id=enrollment.course_id)
    base_access_lesson_ids = _course_base_access_lesson_ids(
        user_id=user_id,
        course_id=enrollment.course_id,
    )
    latest_order = _latest_order(user_id=user_id, course_id=enrollment.course_id)
    completed_count = sum(
        snapshot.is_completed
        for snapshot in progress
        if snapshot.lesson_id in base_access_lesson_ids
    )
    total_count = len(base_access_lesson_ids)
    completed_module_count, total_module_count = _dashboard_module_counts(
        progress=progress,
        base_access_lesson_ids=base_access_lesson_ids,
    )
    next_lesson = _next_accessible_lesson(user_id=user_id, course_id=enrollment.course_id)
    homework_completed_count, homework_total_count, next_homework = _dashboard_homework_snapshot(
        user_id=user_id,
        course_id=enrollment.course_id,
    )
    return CourseDashboardView(
        course=enrollment.course,
        enrollment_status=enrollment.status,
        tariff_label=_tariff_label(enrollment),
        completed_count=completed_count,
        total_count=total_count,
        progress_percent=_dashboard_percent(
            completed_count=completed_count,
            total_count=total_count,
        ),
        completed_module_count=completed_module_count,
        total_module_count=total_module_count,
        homework_completed_count=homework_completed_count,
        homework_total_count=homework_total_count,
        next_lesson=next_lesson,
        next_homework=next_homework,
        recent_actions=_dashboard_recent_actions(
            progress=progress,
            lessons=lessons,
            next_lesson=next_lesson,
            next_homework=next_homework,
        ),
        available_tariffs=_active_tariffs(course_id=enrollment.course_id),
        latest_order=latest_order,
        access_state_label=_access_state_label(enrollment),
        access_state_hint=_access_state_hint(enrollment=enrollment, latest_order=latest_order),
        payment_state_label=_payment_state_label(latest_order),
        access_mode_label=_access_mode_label(enrollment),
        access_mode_hint=_access_mode_hint(enrollment),
        lesson0=_lesson0_for_course(enrollment.course),
        workshop_module=_course_workshop_module(course_id=enrollment.course_id),
    )


def _video_event_properties(
    *,
    lesson: Lesson,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "course_slug": lesson.module.course.slug,
        "module_id": lesson.module_id,
        "lesson_id": lesson.id,
        **dict(extra or {}),
    }


def _record_video_event(
    *,
    request: HttpRequest,
    lesson: Lesson,
    event_name: str,
    properties: dict[str, object] | None = None,
) -> None:
    ORMAnalyticsEventService().record_event(
        name=event_name,
        source_app="media_library",
        actor_identifier=str(request.user.id),
        object_type="lesson",
        object_key=str(lesson.id),
        properties=_video_event_properties(lesson=lesson, extra=properties),
    )


def _playback_error_payload(session: PlaybackSession) -> dict[str, object]:
    reasons = {
        PlaybackState.MISSING: "media_missing",
        PlaybackState.PROCESSING: "media_processing",
        PlaybackState.FAILED: "media_failed",
    }
    return {
        "status": session.state.value,
        "reason": reasons.get(session.state, "media_unavailable"),
        "detail": session.detail,
    }


def _playback_success_payload(session: PlaybackSession) -> dict[str, object]:
    return {
        "status": session.state.value,
        "playback_url": session.playback_url,
        "playback_token": session.ticket_token,
        "expires_at": session.expires_at.isoformat() if session.expires_at else "",
    }


def _json_object_body(request: HttpRequest) -> dict[str, object]:
    if not request.body:
        return {}
    payload = json.loads(request.body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Ожидался JSON-объект.")
    return payload


def _homework_author_identifier(request: HttpRequest) -> str:
    return homework_author_identifier(request.user.id)


def _lesson_detail_context(
    request: HttpRequest,
    *,
    lesson: Lesson,
    progress: LessonProgressSnapshot,
    homework_form_assignment_slug: str = "",
    homework_form_error: str = "",
    homework_form_text: str = "",
) -> dict[str, object]:
    course_completed_count, course_total_count, course_progress_percent = _course_progress_counts(
        user_id=request.user.id,
        course_id=lesson.module.course_id,
    )
    return {
        "lesson": lesson,
        "lesson_code": _lesson_display_code(lesson),
        "course": lesson.module.course,
        "progress": progress,
        "progress_status_label": _progress_status_label(progress),
        "lesson_progress_percent": _lesson_progress_percent(progress),
        "course_completed_count": course_completed_count,
        "course_total_count": course_total_count,
        "course_progress_percent": course_progress_percent,
        "homework_assignments": list_assignment_views_for_lesson(
            lesson_id=lesson.id,
            author_identifier=_homework_author_identifier(request),
        ),
        "homework_completion_gate": check_lesson_homework_gate(
            lesson_id=lesson.id,
            author_identifier=_homework_author_identifier(request),
        ),
        "homework_form_assignment_slug": homework_form_assignment_slug,
        "homework_form_error": homework_form_error,
        "homework_form_text": homework_form_text,
        "module_view": _module_access_view(user_id=request.user.id, module=lesson.module),
        "download_blocks": tuple(
            block for block in lesson.blocks.all() if block.block_type == "download"
        ),
        "next_lesson": _next_accessible_lesson(
            user_id=request.user.id,
            course_id=lesson.module.course_id,
        ),
        "previous_module_lesson": _adjacent_module_lesson(lesson=lesson, offset=-1),
        "next_module_lesson": _adjacent_module_lesson(lesson=lesson, offset=1),
    }


def _previous_homework_gate_decision(
    *,
    user_id: int,
    lesson: Lesson,
    access_decision: AccessDecision,
) -> HomeworkGateDecision | None:
    if access_decision.reason == "staff_role":
        return None
    homework_gate = find_previous_homework_blocker(
        lesson=lesson,
        author_identifier=homework_author_identifier(user_id),
    )
    if homework_gate.allowed:
        return None
    return homework_gate


def _render_homework_locked_lesson(
    request: HttpRequest,
    *,
    lesson: Lesson,
    homework_gate: HomeworkGateDecision,
) -> HttpResponse:
    decision = AccessDecision(
        allowed=False,
        reason="homework_stop_lesson",
    )
    ORMAnalyticsEventService().record_event(
        name="locked_module_clicked",
        source_app="curriculum",
        actor_identifier=str(request.user.id),
        object_type="lesson",
        object_key=str(lesson.id),
        properties={
            "reason": decision.reason,
            "course_slug": lesson.module.course.slug,
            "blocked_lesson_id": homework_gate.lesson_id,
            "assignment_slug": homework_gate.assignment_slug,
            "homework_reason": homework_gate.reason,
        },
    )
    return render(
        request,
        "curriculum/lesson_locked.html",
        {
            "lesson": lesson,
            "decision": decision,
            "locked_reason": (
                f"{homework_gate.reason_label} "
                f"Стоп-урок: {homework_gate.lesson_title} / {homework_gate.assignment_title}."
            ),
        },
        status=403,
    )


@login_required
@require_GET
def learner_dashboard(request: HttpRequest) -> HttpResponse:
    enrollments = tuple(
        Enrollment.objects.select_related("course", "tariff")
        .filter(user_id=request.user.id)
        .order_by("-started_at", "-id")
    )
    courses = tuple(
        _course_dashboard_view(user_id=request.user.id, enrollment=enrollment)
        for enrollment in enrollments
    )
    return render(
        request,
        "curriculum/learner_dashboard.html",
        {
            "courses": courses,
        },
    )


@require_GET
def course_preview(request: HttpRequest, course_slug: str) -> HttpResponse:
    course = get_object_or_404(
        Course.objects.prefetch_related("modules__lessons"),
        slug=course_slug,
    )
    if not request.user.is_authenticated:
        _login_public_preview_lead(request, course=course)
        return redirect("curriculum:course_preview", course_slug=course.slug)

    module_views = tuple(
        _module_access_view(user_id=request.user.id, module=module)
        for module in course.modules.all()
    )
    modules = tuple(sorted(module_views, key=_course_map_sort_key))
    intro_modules = tuple(module for module in modules if module.display_index == "0")
    main_modules = tuple(
        module for module in modules if module.display_index not in {"0", "W"}
    )
    workshop_module_view = next(
        (module for module in modules if module.display_index == "W"),
        None,
    )
    progress = list_progress_for_course(user_id=request.user.id, course_id=course.id)
    visible_lesson_ids = _course_base_access_lesson_ids(
        user_id=request.user.id,
        course_id=course.id,
    )
    lesson0 = _lesson0_for_course(course)
    next_lesson = _next_accessible_lesson(user_id=request.user.id, course_id=course.id)
    enrollment = _active_enrollment(user_id=request.user.id, course_id=course.id)
    latest_order = _latest_order(user_id=request.user.id, course_id=course.id)
    workshop_module = _course_workshop_module(course_id=course.id)
    completed_count = sum(
        snapshot.is_completed
        for snapshot in progress
        if snapshot.lesson_id in visible_lesson_ids
    )
    total_count = len(visible_lesson_ids)
    return render(
        request,
        "curriculum/course_preview.html",
        {
            "course": course,
            "modules": modules,
            "intro_modules": intro_modules,
            "main_modules": main_modules,
            "workshop_module_view": workshop_module_view,
            "completed_count": completed_count,
            "total_count": total_count,
            "course_progress_percent": _dashboard_percent(
                completed_count=completed_count,
                total_count=total_count,
            ),
            "lesson0": lesson0,
            "next_lesson": next_lesson,
            "tariff_label": _tariff_label(enrollment),
            "access_mode_label": _access_mode_label(enrollment),
            "access_mode_hint": _access_mode_hint(enrollment),
            "enrollment_status": enrollment.status if enrollment else "",
            "is_lesson0_only": (
                enrollment is not None and enrollment.status == Enrollment.Status.PREVIEW
            ),
            "tariffs": _active_tariffs(course_id=course.id),
            "latest_order": latest_order,
            "payment_state_label": _payment_state_label(latest_order),
            "workshop_module": workshop_module,
        },
    )


def _module_detail_context(
    *,
    request: HttpRequest,
    module: Module,
    document_acceptance_error: str = "",
) -> dict[str, object]:
    module_view = _module_access_view(user_id=request.user.id, module=module)
    primary_lesson_view = _module_primary_lesson_view(lesson_views=module_view.lessons)
    course_completed_count, course_total_count, course_progress_percent = _course_progress_counts(
        user_id=request.user.id,
        course_id=module.course_id,
    )
    return {
        "course": module.course,
        "module": module,
        "module_view": module_view,
        "workshop_lesson_view": primary_lesson_view,
        "course_completed_count": course_completed_count,
        "course_total_count": course_total_count,
        "course_progress_percent": course_progress_percent,
        "next_lesson": _next_accessible_lesson(
            user_id=request.user.id,
            course_id=module.course_id,
        ),
        "document_acceptance_error": document_acceptance_error,
    }


@login_required
@require_GET
def module_detail(request: HttpRequest, module_id: int) -> HttpResponse:
    module = get_object_or_404(
        Module.objects.select_related("course").prefetch_related("lessons"),
        id=module_id,
    )
    return render(
        request,
        "curriculum/module_detail.html",
        _module_detail_context(request=request, module=module),
    )


@login_required
@require_POST
def module_complete(request: HttpRequest, module_id: int) -> HttpResponse:
    module = get_object_or_404(
        Module.objects.select_related("course").prefetch_related("lessons"),
        id=module_id,
    )
    module_view = _module_access_view(user_id=request.user.id, module=module)
    if not module_view.documents_required:
        return redirect("curriculum:module_detail", module_id=module.id)
    if module_view.documents_accepted:
        return redirect("curriculum:module_detail", module_id=module.id)
    if not module_view.can_accept_documents:
        return render(
            request,
            "curriculum/module_detail.html",
            _module_detail_context(
                request=request,
                module=module,
                document_acceptance_error=(
                    "Сначала завершите все доступные уроки модуля. "
                    "После этого появится переход к следующему блоку."
                ),
            ),
            status=400,
        )
    if request.POST.get("accept_documents") != "on":
        return render(
            request,
            "curriculum/module_detail.html",
            _module_detail_context(
                request=request,
                module=module,
                document_acceptance_error="Поставьте галочку согласия с документами.",
            ),
            status=400,
        )

    _mark_module_documents_accepted(user_id=request.user.id, module=module)
    messages.success(
        request,
        "Документы по модулю подтверждены. Следующий блок откроется по расписанию.",
    )
    next_lesson = _next_accessible_lesson(user_id=request.user.id, course_id=module.course_id)
    if next_lesson is not None and next_lesson.module_id != module.id:
        return redirect("curriculum:lesson_detail", lesson_id=next_lesson.id)
    return redirect("curriculum:course_preview", course_slug=module.course.slug)


@login_required
@require_GET
def lesson_detail(request: HttpRequest, lesson_id: int) -> HttpResponse:
    lesson = get_object_or_404(
        Lesson.objects.select_related("module", "module__course").prefetch_related("blocks"),
        id=lesson_id,
    )
    decision = _effective_lesson_access_decision(user_id=request.user.id, lesson=lesson)
    if not decision.allowed:
        ORMAnalyticsEventService().record_event(
            name="locked_module_clicked",
            source_app="curriculum",
            actor_identifier=str(request.user.id),
            object_type="lesson",
            object_key=str(lesson.id),
            properties={"reason": decision.reason, "course_slug": lesson.module.course.slug},
        )
        return render(
            request,
            "curriculum/lesson_locked.html",
            {"lesson": lesson, "decision": decision, "locked_reason": _locked_reason(decision)},
            status=403,
        )
    homework_gate = _previous_homework_gate_decision(
        user_id=request.user.id,
        lesson=lesson,
        access_decision=decision,
    )
    if homework_gate is not None:
        return _render_homework_locked_lesson(
            request,
            lesson=lesson,
            homework_gate=homework_gate,
        )

    update_progress(
        user_id=request.user.id,
        lesson_id=lesson.id,
        status="opened",
        source="lesson_page",
    )
    if lesson.module.position == 0 and lesson.position == 0:
        ORMAnalyticsEventService().record_event(
            name="lesson0_opened",
            source_app="curriculum",
            actor_identifier=str(request.user.id),
            object_type="lesson",
            object_key=str(lesson.id),
            properties={"course_slug": lesson.module.course.slug},
        )
    progress = get_progress_for_lesson(request.user.id, lesson.id)
    return render(
        request,
        "curriculum/lesson_detail.html",
        _lesson_detail_context(request, lesson=lesson, progress=progress),
    )


@login_required
@require_GET
def lesson_materials(request: HttpRequest, lesson_id: int) -> HttpResponse:
    lesson = get_object_or_404(
        Lesson.objects.select_related("module", "module__course").prefetch_related("blocks"),
        id=lesson_id,
    )
    decision = _effective_lesson_access_decision(user_id=request.user.id, lesson=lesson)
    if not decision.allowed:
        ORMAnalyticsEventService().record_event(
            name="locked_module_clicked",
            source_app="curriculum",
            actor_identifier=str(request.user.id),
            object_type="lesson",
            object_key=str(lesson.id),
            properties={"reason": decision.reason, "course_slug": lesson.module.course.slug},
        )
        return render(
            request,
            "curriculum/lesson_locked.html",
            {"lesson": lesson, "decision": decision, "locked_reason": _locked_reason(decision)},
            status=403,
        )

    progress = get_progress_for_lesson(request.user.id, lesson.id)
    return render(
        request,
        "curriculum/lesson_materials.html",
        {
            **_lesson_detail_context(request, lesson=lesson, progress=progress),
            "download_blocks": tuple(
                block for block in lesson.blocks.all() if block.block_type == "download"
            ),
        },
    )


@login_required
@require_POST
def lesson_homework_submit(request: HttpRequest, lesson_id: int) -> HttpResponse:
    lesson = get_object_or_404(
        Lesson.objects.select_related("module", "module__course").prefetch_related("blocks"),
        id=lesson_id,
    )
    decision = _effective_lesson_access_decision(user_id=request.user.id, lesson=lesson)
    if not decision.allowed:
        ORMAnalyticsEventService().record_event(
            name="locked_module_clicked",
            source_app="curriculum",
            actor_identifier=str(request.user.id),
            object_type="lesson",
            object_key=str(lesson.id),
            properties={"reason": decision.reason, "course_slug": lesson.module.course.slug},
        )
        return render(
            request,
            "curriculum/lesson_locked.html",
            {"lesson": lesson, "decision": decision, "locked_reason": _locked_reason(decision)},
            status=403,
        )
    homework_gate = _previous_homework_gate_decision(
        user_id=request.user.id,
        lesson=lesson,
        access_decision=decision,
    )
    if homework_gate is not None:
        return _render_homework_locked_lesson(
            request,
            lesson=lesson,
            homework_gate=homework_gate,
        )

    assignment_slug = request.POST.get("assignment_slug", "").strip()
    answer_text = request.POST.get("answer_text", "")
    uploaded_files = [
        *request.FILES.getlist("attachments"),
        *request.FILES.getlist("attachment"),
    ]
    assignment = get_object_or_404(
        list_assignments_for_lesson(lesson_id=lesson.id),
        slug=assignment_slug,
    )

    try:
        submission = submit_text_answer(
            assignment=assignment,
            author_identifier=_homework_author_identifier(request),
            answer_text=answer_text,
            attachments=uploaded_files,
        )
    except ValueError as exc:
        progress = update_progress(
            user_id=request.user.id,
            lesson_id=lesson.id,
            status="opened",
            source="lesson_page",
        )
        return render(
            request,
            "curriculum/lesson_detail.html",
            _lesson_detail_context(
                request,
                lesson=lesson,
                progress=progress,
                homework_form_assignment_slug=assignment_slug,
                homework_form_error=str(exc),
                homework_form_text=answer_text,
            ),
            status=400,
        )

    ORMAnalyticsEventService().record_event(
        name="homework_submitted",
        source_app="homework",
        actor_identifier=str(request.user.id),
        object_type="homework_assignment",
        object_key=str(assignment.id),
        properties={
            "assignment_slug": assignment.slug,
            "submission_id": submission.id,
            "attempt_number": submission.attempt_number,
            "course_slug": lesson.module.course.slug,
            "lesson_id": lesson.id,
        },
    )
    return redirect("curriculum:lesson_detail", lesson_id=lesson.id)


@login_required
@require_POST
def lesson_complete(request: HttpRequest, lesson_id: int) -> HttpResponse:
    lesson = get_object_or_404(
        Lesson.objects.select_related("module", "module__course"),
        id=lesson_id,
    )
    decision = _effective_lesson_access_decision(user_id=request.user.id, lesson=lesson)
    if not decision.allowed:
        ORMAnalyticsEventService().record_event(
            name="locked_module_clicked",
            source_app="curriculum",
            actor_identifier=str(request.user.id),
            object_type="lesson",
            object_key=str(lesson.id),
            properties={"reason": decision.reason, "course_slug": lesson.module.course.slug},
        )
        return render(
            request,
            "curriculum/lesson_locked.html",
            {"lesson": lesson, "decision": decision, "locked_reason": _locked_reason(decision)},
            status=403,
        )
    homework_gate = _previous_homework_gate_decision(
        user_id=request.user.id,
        lesson=lesson,
        access_decision=decision,
    )
    if homework_gate is not None:
        return _render_homework_locked_lesson(
            request,
            lesson=lesson,
            homework_gate=homework_gate,
        )
    completion_gate = check_lesson_homework_gate(
        lesson_id=lesson.id,
        author_identifier=_homework_author_identifier(request),
    )
    if not completion_gate.allowed:
        progress = update_progress(
            user_id=request.user.id,
            lesson_id=lesson.id,
            status="opened",
            source="lesson_page",
        )
        return render(
            request,
            "curriculum/lesson_detail.html",
            _lesson_detail_context(request, lesson=lesson, progress=progress),
            status=400,
        )

    progress_record = complete_lesson(
        request.user.id,
        lesson.id,
        source="lesson_player",
        metadata={"course_slug": lesson.module.course.slug},
    )
    _queue_lesson_completed_message(
        user_id=request.user.id,
        progress_id=progress_record.id,
        course_slug=lesson.module.course.slug,
        lesson_id=lesson.id,
        lesson_slug=lesson.slug,
    )
    ORMAnalyticsEventService().record_event(
        name="lesson_completed",
        source_app="curriculum",
        actor_identifier=str(request.user.id),
        object_type="lesson",
        object_key=str(lesson.id),
        properties={"course_slug": lesson.module.course.slug},
    )
    if (
        _is_last_published_lesson_in_module(lesson)
        and _module_documents_required(user_id=request.user.id, module=lesson.module)
        and not _module_documents_accepted(user_id=request.user.id, module=lesson.module)
    ):
        return redirect("curriculum:module_detail", module_id=lesson.module_id)

    next_lesson = _next_accessible_lesson(
        user_id=request.user.id,
        course_id=lesson.module.course_id,
    )
    if next_lesson is not None:
        return redirect("curriculum:lesson_detail", lesson_id=next_lesson.id)
    return redirect("curriculum:course_preview", course_slug=lesson.module.course.slug)


@login_required
@require_GET
def lesson_playback(request: HttpRequest, lesson_id: int) -> JsonResponse:
    lesson = get_object_or_404(
        Lesson.objects.select_related("module", "module__course"),
        id=lesson_id,
    )
    decision = _effective_lesson_access_decision(user_id=request.user.id, lesson=lesson)
    if not decision.allowed:
        return JsonResponse(
            {
                "status": "locked",
                "error": "access_denied",
                "reason": decision.reason,
            },
            status=403,
        )
    homework_gate = _previous_homework_gate_decision(
        user_id=request.user.id,
        lesson=lesson,
        access_decision=decision,
    )
    if homework_gate is not None:
        return JsonResponse(
            {
                "status": "locked",
                "error": "homework_stop_lesson",
                "reason": homework_gate.reason,
                "detail": homework_gate.reason_label,
                "blocked_lesson_id": homework_gate.lesson_id,
            },
            status=403,
        )

    session = PlaybackService().issue_for_lesson(lesson_id=lesson.id)
    if session.is_ready:
        _record_video_event(
            request=request,
            lesson=lesson,
            event_name="video_started",
            properties={
                "attachment_id": session.attachment_id,
                "asset_id": session.asset_id,
                "access_reason": decision.reason,
                "grant_type": decision.grant_type,
            },
        )
        return JsonResponse(_playback_success_payload(session))

    if session.state in {PlaybackState.MISSING, PlaybackState.FAILED}:
        _record_video_event(
            request=request,
            lesson=lesson,
            event_name="video_error",
            properties={
                "state": session.state.value,
                "detail": session.detail,
                "access_reason": decision.reason,
            },
        )

    status_code = 404 if session.state == PlaybackState.MISSING else 409
    return JsonResponse(_playback_error_payload(session), status=status_code)


@login_required
@require_GET
def playback_ticket_status(request: HttpRequest) -> JsonResponse:
    raw_token = request.headers.get("X-Playback-Token") or request.GET.get("token", "")
    if not raw_token:
        return JsonResponse(
            {"status": "missing", "reason": "playback_token_required"},
            status=400,
        )

    try:
        ticket = PlaybackService().get_valid_ticket(raw_token=raw_token)
    except ExpiredPlaybackTicketError:
        ORMAnalyticsEventService().record_event(
            name="video_token_expired",
            source_app="media_library",
            actor_identifier=str(request.user.id),
            object_type="playback_ticket",
            properties={"reason": "playback_ticket_expired"},
        )
        return JsonResponse(
            {"status": "token_expired", "reason": "playback_ticket_expired"},
            status=410,
        )
    except PlaybackTicketNotFoundError:
        return JsonResponse(
            {"status": "missing", "reason": "playback_ticket_missing"},
            status=404,
        )
    except ConsumedPlaybackTicketError:
        return JsonResponse(
            {"status": "failed", "reason": "playback_ticket_consumed"},
            status=409,
        )

    return JsonResponse(
        {
            "status": "ready",
            "expires_at": ticket.expires_at.isoformat(),
            "lesson_id": ticket.attachment.lesson_id,
        }
    )


@login_required
@require_POST
def lesson_video_event(request: HttpRequest, lesson_id: int) -> JsonResponse:
    lesson = get_object_or_404(
        Lesson.objects.select_related("module", "module__course"),
        id=lesson_id,
    )
    decision = _effective_lesson_access_decision(user_id=request.user.id, lesson=lesson)
    if not decision.allowed:
        return JsonResponse(
            {
                "status": "locked",
                "error": "access_denied",
                "reason": decision.reason,
            },
            status=403,
        )
    homework_gate = _previous_homework_gate_decision(
        user_id=request.user.id,
        lesson=lesson,
        access_decision=decision,
    )
    if homework_gate is not None:
        return JsonResponse(
            {
                "status": "locked",
                "error": "homework_stop_lesson",
                "reason": homework_gate.reason,
                "detail": homework_gate.reason_label,
                "blocked_lesson_id": homework_gate.lesson_id,
            },
            status=403,
        )

    try:
        payload = _json_object_body(request)
    except (JSONDecodeError, ValueError):
        return JsonResponse(
            {"status": "failed", "reason": "invalid_json_body"},
            status=400,
        )

    event_type = str(payload.get("event", ""))
    allowed_events = {"started", "progressed", "completed", "error"}
    if event_type not in allowed_events:
        return JsonResponse(
            {"status": "failed", "reason": "unsupported_video_event"},
            status=400,
        )

    event_properties = {
        "position_seconds": payload.get("position_seconds"),
        "percent": payload.get("percent"),
        "reason": payload.get("reason"),
        "access_reason": decision.reason,
    }
    _record_video_event(
        request=request,
        lesson=lesson,
        event_name=f"video_{event_type}",
        properties=event_properties,
    )
    return JsonResponse({"status": "recorded", "event": event_type})
