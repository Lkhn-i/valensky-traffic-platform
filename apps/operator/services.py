from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone

from apps.access_control.models import AccessGrant, PreviewAccessGrant
from apps.access_control.services import AccessDecision, check_access
from apps.accounts.models import LeadProfile, UserRole, UserTelegramIdentity
from apps.accounts.services import user_has_role
from apps.commerce.models import Order
from apps.curriculum.models import Course, Lesson, LessonBlock, Module
from apps.diagnostic_handoff.models import DiagnosticHandoff
from apps.events.models import AuditLog
from apps.events.services import AuditLogService, ORMAuditLogService
from apps.homework.models import HomeworkReview, HomeworkSubmission
from apps.homework.services import find_previous_homework_blocker, homework_author_identifier
from apps.learning_state.models import ProgressRecord
from apps.media_library.models import LessonMediaAttachment
from apps.notifications.models import NotificationJob
from apps.notifications.services import enqueue_notification

OPERATOR_ROLE_CODES = ("super_admin", "admin", "manager")
LEARNER_ROLE_CODES = ("student", "lead")

__all__ = [
    "ContentPublicationResult",
    "ContentReadinessIssue",
    "ContentReadinessSnapshot",
    "HomeworkReviewDecisionResult",
    "HomeworkReviewQueueItem",
    "HomeworkReviewQueueSnapshot",
    "LearnerContactSnapshot",
    "LearnerAccessGrantSnapshot",
    "LearnerAccessDiagnosisSnapshot",
    "LearnerListItem",
    "LearnerOrderSnapshot",
    "LearnerProgressSnapshot",
    "LearnerSupportSnapshot",
    "OPERATOR_ROLE_CODES",
    "OperatorDashboardMetrics",
    "OperatorPermissionDecision",
    "check_operator_permissions",
    "draft_course",
    "draft_lesson",
    "draft_module",
    "enqueue_learner_access_link",
    "get_homework_review_queue",
    "get_content_readiness_snapshot",
    "get_learner_support_snapshot",
    "get_operator_dashboard_metrics",
    "list_learner_support_items",
    "publish_course",
    "publish_lesson",
    "publish_module",
    "record_operator_action",
    "review_homework_submission",
    "require_operator_permissions",
]


@dataclass(frozen=True, slots=True)
class OperatorPermissionDecision:
    user_id: int
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ContentPublicationResult:
    content_id: int
    content_type: str
    target_key: str
    publication_status: str
    updated: bool
    audit_log_id: int | None


@dataclass(frozen=True, slots=True)
class ContentReadinessIssue:
    level: str
    message: str


@dataclass(frozen=True, slots=True)
class ContentReadinessSnapshot:
    content_type: str
    content_id: int
    can_publish: bool
    issues: tuple[ContentReadinessIssue, ...]


@dataclass(frozen=True, slots=True)
class LearnerOrderSnapshot:
    order_id: int
    order_number: str
    status: str
    course_slug: str
    tariff_code: str
    access_grant_id: int | None
    amount: Decimal
    currency: str
    created_at: datetime
    paid_at: datetime | None


@dataclass(frozen=True, slots=True)
class LearnerAccessGrantSnapshot:
    grant_id: int
    grant_kind: str
    status: str
    course_slug: str
    lesson_slug: str
    tariff_code: str
    source: str
    starts_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class LearnerProgressSnapshot:
    progress_id: int
    course_slug: str
    module_slug: str
    lesson_slug: str
    status: str
    first_opened_at: datetime | None
    last_opened_at: datetime | None
    completed_at: datetime | None
    source: str


@dataclass(frozen=True, slots=True)
class LearnerAccessDiagnosisSnapshot:
    lesson_id: int
    course_slug: str
    module_slug: str
    lesson_slug: str
    lesson_title: str
    allowed: bool
    reason: str
    reason_label: str
    grant_type: str


@dataclass(frozen=True, slots=True)
class LearnerListItem:
    user_id: int
    username: str
    display_name: str
    roles: tuple[str, ...]
    order_count: int
    active_grant_count: int
    completed_lessons: int


@dataclass(frozen=True, slots=True)
class LearnerContactSnapshot:
    email: str
    login: str
    phone: str
    telegram_username: str
    telegram_link: str
    telegram_id: int | None = None

    @property
    def has_any(self) -> bool:
        return any(
            (
                self.email,
                self.login,
                self.phone,
                self.telegram_username,
                self.telegram_link,
                self.telegram_id,
            )
        )


@dataclass(frozen=True, slots=True)
class LearnerSupportSnapshot:
    user_id: int
    username: str
    display_name: str
    roles: tuple[str, ...]
    orders: tuple[LearnerOrderSnapshot, ...]
    access_grants: tuple[LearnerAccessGrantSnapshot, ...]
    progress: tuple[LearnerProgressSnapshot, ...]
    access_diagnostics: tuple[LearnerAccessDiagnosisSnapshot, ...]
    contacts: LearnerContactSnapshot


@dataclass(frozen=True, slots=True)
class HomeworkReviewQueueItem:
    submission_id: int
    assignment_slug: str
    assignment_title: str
    author_identifier: str
    attempt_number: int
    submission_state: str
    submitted_at: datetime | None
    author_user_id: int | None = None
    author_display_name: str = ""
    author_contacts: LearnerContactSnapshot | None = None
    answer_preview: str = ""


@dataclass(frozen=True, slots=True)
class HomeworkReviewQueueSnapshot:
    pending_count: int
    items: tuple[HomeworkReviewQueueItem, ...]


@dataclass(frozen=True, slots=True)
class HomeworkReviewDecisionResult:
    submission_id: int
    review_id: int
    submission_state: str
    decision: str
    audit_log_id: int
    notification_job_id: int


@dataclass(frozen=True, slots=True)
class OperatorDashboardMetrics:
    total_users: int
    operator_users: int
    learner_users: int
    paid_orders: int
    pending_orders: int
    active_paid_access_grants: int
    active_preview_access_grants: int
    published_courses: int
    draft_courses: int
    published_lessons: int
    completed_lessons: int
    pending_homework_reviews: int


def check_operator_permissions(*, user_id: int) -> OperatorPermissionDecision:
    get_user_model().objects.only("id").get(id=user_id)
    if user_has_role(user_id, OPERATOR_ROLE_CODES):
        return OperatorPermissionDecision(
            user_id=user_id,
            allowed=True,
            reason="operator_role",
        )
    return OperatorPermissionDecision(
        user_id=user_id,
        allowed=False,
        reason="missing_operator_role",
    )


def require_operator_permissions(
    *,
    user_id: int,
    action: str = "выполнять операторские действия",
) -> None:
    decision = check_operator_permissions(user_id=user_id)
    if decision.allowed:
        return
    raise PermissionError(f"Пользователь {user_id} не может: {action}.")


def record_operator_action(
    *,
    action: str,
    actor_user_id: int | None,
    target_type: str,
    target_key: str,
    result: str = "success",
    message: str = "",
    payload: Mapping[str, Any] | None = None,
    audit_log_service: AuditLogService | None = None,
) -> AuditLog:
    service = audit_log_service if audit_log_service is not None else ORMAuditLogService()
    return service.record_log(
        action=action,
        result=result,
        actor_identifier=str(actor_user_id or ""),
        target_type=target_type,
        target_key=target_key,
        message=message,
        payload=dict(payload or {}),
    )


def _publication_message(*, target_type: str, target_key: str, publication_status: str) -> str:
    return f"Статус {target_type} {target_key} изменён на {publication_status}."


def _readiness_issue(level: str, message: str) -> ContentReadinessIssue:
    return ContentReadinessIssue(level=level, message=message)


def _lesson_readiness_issues(lesson: Lesson) -> tuple[ContentReadinessIssue, ...]:
    issues: list[ContentReadinessIssue] = []
    if lesson.module.publication_status != Module.PublicationStatus.PUBLISHED:
        issues.append(_readiness_issue("error", "Родительский модуль ещё не опубликован."))
    if lesson.module.course.publication_status != Course.PublicationStatus.PUBLISHED:
        issues.append(_readiness_issue("error", "Курс урока ещё не опубликован."))
    if not LessonBlock.objects.filter(lesson=lesson).exists():
        issues.append(_readiness_issue("error", "В уроке нет ни одного блока контента."))
    if not LessonMediaAttachment.objects.filter(
        lesson=lesson,
        purpose=LessonMediaAttachment.Purpose.PRIMARY_VIDEO,
        media_asset__availability_status="ready",
    ).exists():
        issues.append(_readiness_issue("warning", "Нет готового основного видео."))
    if LessonBlock.objects.filter(lesson=lesson, block_type=LessonBlock.BlockType.DOWNLOAD).filter(
        Q(payload__resource_slug__isnull=True) | Q(payload__resource_slug="")
    ).exists():
        issues.append(
            _readiness_issue(
                "warning",
                "У одного из файловых блоков нет resource_slug для защищённого материала.",
            )
        )
    return tuple(issues)


def _module_readiness_issues(module: Module) -> tuple[ContentReadinessIssue, ...]:
    issues: list[ContentReadinessIssue] = []
    if module.course.publication_status != Course.PublicationStatus.PUBLISHED:
        issues.append(_readiness_issue("error", "Курс модуля ещё не опубликован."))
    if not Lesson.objects.filter(module=module).exists():
        issues.append(_readiness_issue("warning", "В модуле пока нет уроков."))
    if Lesson.objects.filter(
        module=module,
        publication_status=Lesson.PublicationStatus.DRAFT,
    ).exists():
        issues.append(_readiness_issue("warning", "В модуле есть уроки в черновике."))
    return tuple(issues)


def _course_readiness_issues(course: Course) -> tuple[ContentReadinessIssue, ...]:
    issues: list[ContentReadinessIssue] = []
    if not Module.objects.filter(course=course).exists():
        issues.append(_readiness_issue("error", "В курсе нет модулей."))
    if Module.objects.filter(
        course=course,
        publication_status=Module.PublicationStatus.DRAFT,
    ).exists():
        issues.append(_readiness_issue("warning", "В курсе есть модули в черновике."))
    if not Lesson.objects.filter(module__course=course).exists():
        issues.append(_readiness_issue("warning", "В курсе пока нет уроков."))
    return tuple(issues)


def _readiness_snapshot(
    *,
    content_type: str,
    content_id: int,
    issues: tuple[ContentReadinessIssue, ...],
) -> ContentReadinessSnapshot:
    return ContentReadinessSnapshot(
        content_type=content_type,
        content_id=content_id,
        can_publish=not any(issue.level == "error" for issue in issues),
        issues=issues,
    )


def get_content_readiness_snapshot(
    *,
    content_type: str,
    content_id: int,
) -> ContentReadinessSnapshot:
    if content_type in {"curriculum.Course", "course"}:
        course = Course.objects.get(id=content_id)
        return _readiness_snapshot(
            content_type="curriculum.Course",
            content_id=course.id,
            issues=_course_readiness_issues(course),
        )
    if content_type in {"curriculum.Module", "module"}:
        module = Module.objects.select_related("course").get(id=content_id)
        return _readiness_snapshot(
            content_type="curriculum.Module",
            content_id=module.id,
            issues=_module_readiness_issues(module),
        )
    if content_type in {"curriculum.Lesson", "lesson"}:
        lesson = Lesson.objects.select_related("module", "module__course").get(id=content_id)
        return _readiness_snapshot(
            content_type="curriculum.Lesson",
            content_id=lesson.id,
            issues=_lesson_readiness_issues(lesson),
        )
    raise ValueError(f"Неподдерживаемый тип контента для проверки: {content_type!r}")


def _require_publish_ready(*, target_type: str, content_id: int) -> None:
    readiness = get_content_readiness_snapshot(
        content_type=target_type,
        content_id=content_id,
    )
    if readiness.can_publish:
        return
    error_messages = [issue.message for issue in readiness.issues if issue.level == "error"]
    raise ValueError("Нельзя опубликовать: " + " ".join(error_messages))


@transaction.atomic
def _set_publication_status(
    *,
    queryset: QuerySet[Any],
    content_id: int,
    publication_status: str,
    actor_user_id: int,
    action: str,
    target_type: str,
    message: str = "",
    audit_log_service: AuditLogService | None = None,
) -> ContentPublicationResult:
    require_operator_permissions(user_id=actor_user_id, action=action)
    content = queryset.select_for_update().get(id=content_id)
    if publication_status == "published":
        _require_publish_ready(target_type=target_type, content_id=content.id)

    updated = False
    if content.publication_status != publication_status:
        content.publication_status = publication_status
        content.save(update_fields=["publication_status", "updated_at"])
        updated = True

    target_key = str(content.slug)
    audit_log = record_operator_action(
        action=action,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_key=target_key,
        message=message or _publication_message(
            target_type=target_type,
            target_key=target_key,
            publication_status=publication_status,
        ),
        payload={
            "content_id": content.id,
            "publication_status": publication_status,
            "updated": updated,
        },
        audit_log_service=audit_log_service,
    )
    return ContentPublicationResult(
        content_id=content.id,
        content_type=target_type,
        target_key=target_key,
        publication_status=str(content.publication_status),
        updated=updated,
        audit_log_id=audit_log.id,
    )


def draft_course(
    *,
    course_id: int,
    actor_user_id: int,
    message: str = "",
    audit_log_service: AuditLogService | None = None,
) -> ContentPublicationResult:
    return _set_publication_status(
        queryset=Course.objects.all(),
        content_id=course_id,
        publication_status="draft",
        actor_user_id=actor_user_id,
        action="operator.course.draft",
        target_type="curriculum.Course",
        message=message,
        audit_log_service=audit_log_service,
    )


def publish_course(
    *,
    course_id: int,
    actor_user_id: int,
    message: str = "",
    audit_log_service: AuditLogService | None = None,
) -> ContentPublicationResult:
    return _set_publication_status(
        queryset=Course.objects.all(),
        content_id=course_id,
        publication_status="published",
        actor_user_id=actor_user_id,
        action="operator.course.publish",
        target_type="curriculum.Course",
        message=message,
        audit_log_service=audit_log_service,
    )


def draft_module(
    *,
    module_id: int,
    actor_user_id: int,
    message: str = "",
    audit_log_service: AuditLogService | None = None,
) -> ContentPublicationResult:
    return _set_publication_status(
        queryset=Module.objects.all(),
        content_id=module_id,
        publication_status="draft",
        actor_user_id=actor_user_id,
        action="operator.module.draft",
        target_type="curriculum.Module",
        message=message,
        audit_log_service=audit_log_service,
    )


def publish_module(
    *,
    module_id: int,
    actor_user_id: int,
    message: str = "",
    audit_log_service: AuditLogService | None = None,
) -> ContentPublicationResult:
    return _set_publication_status(
        queryset=Module.objects.all(),
        content_id=module_id,
        publication_status="published",
        actor_user_id=actor_user_id,
        action="operator.module.publish",
        target_type="curriculum.Module",
        message=message,
        audit_log_service=audit_log_service,
    )


def draft_lesson(
    *,
    lesson_id: int,
    actor_user_id: int,
    message: str = "",
    audit_log_service: AuditLogService | None = None,
) -> ContentPublicationResult:
    return _set_publication_status(
        queryset=Lesson.objects.all(),
        content_id=lesson_id,
        publication_status="draft",
        actor_user_id=actor_user_id,
        action="operator.lesson.draft",
        target_type="curriculum.Lesson",
        message=message,
        audit_log_service=audit_log_service,
    )


def publish_lesson(
    *,
    lesson_id: int,
    actor_user_id: int,
    message: str = "",
    audit_log_service: AuditLogService | None = None,
) -> ContentPublicationResult:
    return _set_publication_status(
        queryset=Lesson.objects.all(),
        content_id=lesson_id,
        publication_status="published",
        actor_user_id=actor_user_id,
        action="operator.lesson.publish",
        target_type="curriculum.Lesson",
        message=message,
        audit_log_service=audit_log_service,
    )


def _access_window(now: datetime) -> Q:
    return Q(starts_at__lte=now) & (Q(expires_at__isnull=True) | Q(expires_at__gt=now))


def _pending_homework_submission_queryset() -> QuerySet[HomeworkSubmission]:
    review_exists = HomeworkReview.objects.filter(submission_id=OuterRef("pk"))
    return (
        HomeworkSubmission.objects.select_related("assignment")
        .annotate(has_reviews=Exists(review_exists))
        .filter(
            submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
            has_reviews=False,
        )
        .order_by("submitted_at", "id")
    )


CONTACT_EMAIL_KEYS = ("email",)
CONTACT_PHONE_KEYS = ("phone", "phone_number", "contact_phone", "tel", "telephone")
CONTACT_LOGIN_KEYS = ("username", "login", "user_name")
CONTACT_TELEGRAM_USERNAME_KEYS = (
    "telegram_username",
    "tg_username",
    "telegram_login",
    "telegram_handle",
)
CONTACT_TELEGRAM_LINK_KEYS = ("telegram_link", "tg_link", "telegram_url", "telegram_profile_url")
CONTACT_TELEGRAM_ID_KEYS = ("telegram_id", "tg_user_id", "tg_id")
SUBMISSION_TEXT_KEYS = ("text_answer", "answer", "message", "text", "content")
SUBMISSION_PREVIEW_LENGTH = 240


def _clean_contact_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int):
        return str(value)
    return ""


def _first_nested_value(payload: object, *, keys: tuple[str, ...]) -> str:
    key_set = {key.lower() for key in keys}
    queue: list[object] = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, Mapping):
            for raw_key, value in current.items():
                if isinstance(raw_key, str) and raw_key.lower() in key_set:
                    normalized_value = _clean_contact_text(value)
                    if normalized_value:
                        return normalized_value
            for value in current.values():
                if isinstance(value, (Mapping, list, tuple)):
                    queue.append(value)
        elif isinstance(current, (list, tuple)):
            for value in current:
                if isinstance(value, (Mapping, list, tuple)):
                    queue.append(value)
    return ""


def _normalize_telegram_username(username: str) -> str:
    return username.strip().lstrip("@")


def _resolve_telegram_link(*, username: str, explicit_link: str) -> str:
    if explicit_link:
        return explicit_link
    if username:
        return f"https://t.me/{username}"
    return ""


def _get_optional_lead_profile(user: Any) -> LeadProfile | None:
    try:
        return user.lead_profile
    except LeadProfile.DoesNotExist:
        return None


def _latest_telegram_identity(user: Any) -> UserTelegramIdentity | None:
    identities = list(user.telegram_identities.all())
    if not identities:
        return None
    return max(identities, key=lambda identity: (identity.updated_at, identity.id))


def _latest_diagnostic_handoff(user: Any) -> DiagnosticHandoff | None:
    handoffs = list(user.diagnostic_handoffs.all())
    if not handoffs:
        return None
    return max(handoffs, key=lambda handoff: (handoff.submitted_at, handoff.id))


def _build_learner_contact_snapshot(user: Any) -> LearnerContactSnapshot:
    lead_profile = _get_optional_lead_profile(user)
    lead_metadata = dict(lead_profile.metadata) if lead_profile is not None else {}
    diagnostic_handoff = _latest_diagnostic_handoff(user)
    diagnostic_payload = (
        dict(diagnostic_handoff.raw_payload) if diagnostic_handoff is not None else {}
    )
    telegram_identity = _latest_telegram_identity(user)

    login = user.get_username().strip()
    email = (
        user.email.strip()
        or _first_nested_value(lead_metadata, keys=CONTACT_EMAIL_KEYS)
        or _first_nested_value(diagnostic_payload, keys=CONTACT_EMAIL_KEYS)
    )
    phone = (
        user.phone.strip()
        or _first_nested_value(lead_metadata, keys=CONTACT_PHONE_KEYS)
        or _first_nested_value(diagnostic_payload, keys=CONTACT_PHONE_KEYS)
    )
    telegram_username = (
        _normalize_telegram_username(telegram_identity.username)
        if telegram_identity is not None and telegram_identity.username
        else ""
    )
    if not telegram_username:
        telegram_username = _normalize_telegram_username(
            _first_nested_value(lead_metadata, keys=CONTACT_TELEGRAM_USERNAME_KEYS)
            or _first_nested_value(diagnostic_payload, keys=CONTACT_TELEGRAM_USERNAME_KEYS)
        )
    explicit_telegram_link = (
        _first_nested_value(lead_metadata, keys=CONTACT_TELEGRAM_LINK_KEYS)
        or _first_nested_value(diagnostic_payload, keys=CONTACT_TELEGRAM_LINK_KEYS)
    )
    telegram_id = telegram_identity.telegram_id if telegram_identity is not None else None
    if telegram_id is None:
        raw_telegram_id = (
            _first_nested_value(lead_metadata, keys=CONTACT_TELEGRAM_ID_KEYS)
            or _first_nested_value(diagnostic_payload, keys=CONTACT_TELEGRAM_ID_KEYS)
        )
        if raw_telegram_id:
            try:
                telegram_id = int(raw_telegram_id)
            except ValueError:
                telegram_id = None

    return LearnerContactSnapshot(
        email=email,
        login=login,
        phone=phone,
        telegram_username=telegram_username,
        telegram_link=_resolve_telegram_link(
            username=telegram_username,
            explicit_link=explicit_telegram_link,
        ),
        telegram_id=telegram_id,
    )


def _parse_homework_author_user_id(author_identifier: str) -> int | None:
    if not author_identifier.startswith("user:"):
        return None
    raw_user_id = author_identifier.split(":", 1)[1].strip()
    if not raw_user_id.isdigit():
        return None
    user_id = int(raw_user_id)
    return user_id if user_id > 0 else None


def _queue_users_by_author_identifier(
    submissions: tuple[HomeworkSubmission, ...],
) -> dict[str, Any]:
    identifiers = {submission.author_identifier for submission in submissions}
    lookup_user_ids = {
        user_id
        for user_id in (
            _parse_homework_author_user_id(author_identifier)
            for author_identifier in identifiers
        )
        if user_id is not None
    }
    lookup_usernames = {
        author_identifier
        for author_identifier in identifiers
        if _parse_homework_author_user_id(author_identifier) is None
    }

    filters = Q()
    if lookup_user_ids:
        filters |= Q(id__in=lookup_user_ids)
    if lookup_usernames:
        filters |= Q(username__in=lookup_usernames) | Q(email__in=lookup_usernames)
    if not filters.children:
        return {}

    users = (
        get_user_model()
        .objects.filter(filters)
        .select_related("lead_profile")
        .prefetch_related("telegram_identities", "diagnostic_handoffs")
    )
    users_by_id = {user.id: user for user in users}
    users_by_login = {user.get_username(): user for user in users}
    users_by_email = {user.email: user for user in users if user.email}

    resolved_users: dict[str, Any] = {}
    for author_identifier in identifiers:
        user_id = _parse_homework_author_user_id(author_identifier)
        user = users_by_id.get(user_id) if user_id is not None else None
        if user is None:
            user = users_by_login.get(author_identifier) or users_by_email.get(author_identifier)
        if user is not None:
            resolved_users[author_identifier] = user
    return resolved_users


def _submission_text_preview(submission: HomeworkSubmission) -> str:
    raw_text = _first_nested_value(submission.payload, keys=SUBMISSION_TEXT_KEYS)
    if not raw_text:
        raw_text = submission.notes.strip()
    if not raw_text and submission.payload not in ({}, [], (), None):
        try:
            raw_text = json.dumps(submission.payload, ensure_ascii=False, sort_keys=True)
        except TypeError:
            raw_text = str(submission.payload)
    normalized_text = " ".join(raw_text.split())
    if len(normalized_text) <= SUBMISSION_PREVIEW_LENGTH:
        return normalized_text
    return normalized_text[: SUBMISSION_PREVIEW_LENGTH - 3].rstrip() + "..."


ACCESS_REASON_LABELS = {
    "staff_role": "Доступ открыт по роли команды.",
    "paid_access_grant": "Доступ открыт по активной оплате.",
    "lesson0_preview_grant": "Открыт пробный Урок 0 после диагностики.",
    "course_unpublished": "Курс в черновике и не доступен ученику.",
    "module_unpublished": "Модуль в черновике и не доступен ученику.",
    "lesson_unpublished": "Урок в черновике и не доступен ученику.",
    "not_in_tariff_entitlements": "Текущий тариф не включает этот урок.",
    "missing_paid_access_grant": "Нет активного платного доступа к курсу.",
    "homework_stop_lesson": "Доступ остановлен до принятой домашки в предыдущем уроке.",
}


def _diagnostic_courses_for_user(user_id: int) -> tuple[Course, ...]:
    course_ids = set(
        Order.objects.filter(user_id=user_id).values_list("course_id", flat=True)
    )
    course_ids.update(
        AccessGrant.objects.filter(user_id=user_id).values_list("course_id", flat=True)
    )
    course_ids.update(
        PreviewAccessGrant.objects.filter(user_id=user_id).values_list("course_id", flat=True)
    )
    course_ids.update(
        ProgressRecord.objects.filter(user_id=user_id).values_list("course_id", flat=True)
    )

    if course_ids:
        return tuple(
            Course.objects.filter(id__in=course_ids).order_by("position", "title", "id")
        )
    return tuple(
        Course.objects.filter(publication_status=Course.PublicationStatus.PUBLISHED).order_by(
            "position",
            "title",
            "id",
        )[:5]
    )


def _diagnostic_lessons_for_course(course: Course) -> tuple[Lesson, ...]:
    return tuple(
        Lesson.objects.select_related("module", "module__course")
        .filter(module__course=course)
        .order_by("module__position", "position", "id")[:12]
    )


def _latest_paid_grant_for_course(*, user_id: int, course_id: int) -> AccessGrant | None:
    return (
        AccessGrant.objects.filter(user_id=user_id, course_id=course_id)
        .select_related("tariff")
        .order_by(*AccessGrant._meta.ordering)
        .first()
    )


def _latest_order_for_course(*, user_id: int, course_id: int) -> Order | None:
    return (
        Order.objects.filter(user_id=user_id, course_id=course_id)
        .select_related("tariff")
        .order_by(*Order._meta.ordering)
        .first()
    )


def _has_preview_for_course(*, user_id: int, course_id: int) -> bool:
    now = timezone.now()
    return PreviewAccessGrant.objects.filter(
        user_id=user_id,
        course_id=course_id,
        starts_at__lte=now,
        expires_at__gt=now,
        status=PreviewAccessGrant.Status.ACTIVE,
        revoked_at__isnull=True,
    ).exists()


def _access_reason_label(
    *,
    user_id: int,
    lesson: Lesson,
    decision: AccessDecision,
) -> str:
    if decision.allowed:
        return ACCESS_REASON_LABELS.get(decision.reason, "Доступ открыт.")
    if decision.reason == "not_in_tariff_entitlements":
        active_tariffs = tuple(
            grant.tariff.title
            for grant in AccessGrant.objects.filter(
                _access_window(timezone.now()),
                user_id=user_id,
                course_id=lesson.module.course_id,
                status=AccessGrant.Status.ACTIVE,
                revoked_at__isnull=True,
            ).select_related("tariff")
            if grant.tariff is not None
        )
        if active_tariffs:
            return (
                "Есть активный доступ, но тариф не включает этот урок. "
                f"Активный тариф: {', '.join(active_tariffs)}."
            )
    if decision.reason == "missing_paid_access_grant":
        latest_grant = _latest_paid_grant_for_course(
            user_id=user_id,
            course_id=lesson.module.course_id,
        )
        if latest_grant is not None:
            if (
                latest_grant.revoked_at is not None
                or latest_grant.status == AccessGrant.Status.REVOKED
            ):
                return "Платный доступ был отозван."
            if latest_grant.status == AccessGrant.Status.FROZEN:
                return "Платный доступ заморожен."
            if latest_grant.status == AccessGrant.Status.EXPIRED:
                return "Платный доступ истёк."
            if latest_grant.expires_at is not None and latest_grant.expires_at <= timezone.now():
                return "Платный доступ истёк по сроку действия."
            if latest_grant.starts_at > timezone.now():
                return "Платный доступ ещё не начался."
        if _has_preview_for_course(user_id=user_id, course_id=lesson.module.course_id):
            return "Есть только пробный доступ к Уроку 0; этот урок требует оплату."
        latest_order = _latest_order_for_course(user_id=user_id, course_id=lesson.module.course_id)
        if latest_order is not None:
            if latest_order.status in {Order.Status.CREATED, Order.Status.PENDING}:
                return "Заказ создан, но платёж ещё не подтверждён."
            if latest_order.status == Order.Status.FAILED:
                return "Последний заказ не был оплачен."
            if latest_order.status == Order.Status.REFUNDED:
                return "Последний оплаченный заказ был возвращён."
            if latest_order.status == Order.Status.DISPUTED:
                return "Последний заказ находится на проверке."
    return ACCESS_REASON_LABELS.get(decision.reason, "Доступ закрыт.")


def _diagnose_learner_access(user_id: int) -> tuple[LearnerAccessDiagnosisSnapshot, ...]:
    diagnostics: list[LearnerAccessDiagnosisSnapshot] = []
    for course in _diagnostic_courses_for_user(user_id):
        for lesson in _diagnostic_lessons_for_course(course):
            decision = check_access(user_id=user_id, lesson_id=lesson.id)
            reason = decision.reason
            reason_label = _access_reason_label(
                user_id=user_id,
                lesson=lesson,
                decision=decision,
            )
            grant_type = decision.grant_type
            allowed = decision.allowed
            if allowed and decision.reason != "staff_role":
                homework_gate = find_previous_homework_blocker(
                    lesson=lesson,
                    author_identifier=homework_author_identifier(user_id),
                )
                if not homework_gate.allowed:
                    allowed = False
                    reason = "homework_stop_lesson"
                    reason_label = (
                        f"{homework_gate.reason_label} "
                        f"Стоп-урок: {homework_gate.lesson_title} / "
                        f"{homework_gate.assignment_title}."
                    )
                    grant_type = "homework"
            diagnostics.append(
                LearnerAccessDiagnosisSnapshot(
                    lesson_id=lesson.id,
                    course_slug=lesson.module.course.slug,
                    module_slug=lesson.module.slug,
                    lesson_slug=lesson.slug,
                    lesson_title=lesson.title,
                    allowed=allowed,
                    reason=reason,
                    reason_label=reason_label,
                    grant_type=grant_type,
                )
            )
    return tuple(diagnostics)


def get_learner_support_snapshot(*, user_id: int) -> LearnerSupportSnapshot:
    user = (
        get_user_model()
        .objects.select_related("lead_profile")
        .prefetch_related("telegram_identities", "diagnostic_handoffs")
        .get(id=user_id)
    )

    roles = tuple(
        UserRole.objects.filter(user_id=user_id)
        .select_related("role")
        .order_by("role__code")
        .values_list("role__code", flat=True)
    )
    orders = tuple(
        LearnerOrderSnapshot(
            order_id=order.id,
            order_number=order.number,
            status=str(order.status),
            course_slug=order.course.slug,
            tariff_code=order.tariff.code,
            access_grant_id=order.access_grant_id,
            amount=order.amount,
            currency=order.currency,
            created_at=order.created_at,
            paid_at=order.paid_at,
        )
        for order in Order.objects.filter(user_id=user_id)
        .select_related("course", "tariff", "access_grant")
        .order_by(*Order._meta.ordering)
    )

    access_grants: list[LearnerAccessGrantSnapshot] = []
    for grant in (
        AccessGrant.objects.filter(user_id=user_id)
        .select_related("course", "tariff")
        .order_by(*AccessGrant._meta.ordering)
    ):
        access_grants.append(
            LearnerAccessGrantSnapshot(
                grant_id=grant.id,
                grant_kind="paid",
                status=str(grant.status),
                course_slug=grant.course.slug,
                lesson_slug="",
                tariff_code=grant.tariff.code if grant.tariff is not None else "",
                source=str(grant.source),
                starts_at=grant.starts_at,
                expires_at=grant.expires_at,
                revoked_at=grant.revoked_at,
            )
        )
    for grant in (
        PreviewAccessGrant.objects.filter(user_id=user_id)
        .select_related("course", "lesson")
        .order_by(*PreviewAccessGrant._meta.ordering)
    ):
        access_grants.append(
            LearnerAccessGrantSnapshot(
                grant_id=grant.id,
                grant_kind="preview",
                status=str(grant.status),
                course_slug=grant.course.slug,
                lesson_slug=grant.lesson.slug,
                tariff_code="",
                source="preview",
                starts_at=grant.starts_at,
                expires_at=grant.expires_at,
                revoked_at=grant.revoked_at,
            )
        )
    access_grants.sort(
        key=lambda snapshot: (snapshot.starts_at, snapshot.grant_id, snapshot.grant_kind),
        reverse=True,
    )

    progress = tuple(
        LearnerProgressSnapshot(
            progress_id=record.id,
            course_slug=record.course.slug,
            module_slug=record.module.slug,
            lesson_slug=record.lesson.slug,
            status=str(record.status),
            first_opened_at=record.first_opened_at,
            last_opened_at=record.last_opened_at,
            completed_at=record.completed_at,
            source=record.source,
        )
        for record in ProgressRecord.objects.filter(user_id=user_id)
        .select_related("course", "module", "lesson")
        .order_by(*ProgressRecord._meta.ordering)
    )

    return LearnerSupportSnapshot(
        user_id=user.id,
        username=user.get_username(),
        display_name=user.display_name or user.get_username(),
        roles=roles,
        orders=orders,
        access_grants=tuple(access_grants),
        progress=progress,
        access_diagnostics=_diagnose_learner_access(user_id),
        contacts=_build_learner_contact_snapshot(user),
    )


def list_learner_support_items(*, query: str = "", limit: int = 50) -> tuple[LearnerListItem, ...]:
    queryset = get_user_model().objects.prefetch_related("role_links__role").order_by("id")
    query = query.strip()
    if query:
        queryset = queryset.filter(
            Q(username__icontains=query)
            | Q(display_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )

    items: list[LearnerListItem] = []
    for user in queryset[:limit]:
        role_codes = tuple(
            sorted(role_link.role.code for role_link in user.role_links.all())
        )
        if not set(role_codes).intersection(LEARNER_ROLE_CODES):
            continue
        items.append(
            LearnerListItem(
                user_id=user.id,
                username=user.get_username(),
                display_name=user.display_name or user.get_username(),
                roles=role_codes,
                order_count=Order.objects.filter(user_id=user.id).count(),
                active_grant_count=AccessGrant.objects.filter(
                    user_id=user.id,
                    status=AccessGrant.Status.ACTIVE,
                    revoked_at__isnull=True,
                ).count(),
                completed_lessons=ProgressRecord.objects.filter(
                    user_id=user.id,
                    status=ProgressRecord.Status.COMPLETED,
                ).count(),
            )
        )
    return tuple(items)


def get_homework_review_queue() -> HomeworkReviewQueueSnapshot:
    submissions = tuple(_pending_homework_submission_queryset())
    users_by_author_identifier = _queue_users_by_author_identifier(submissions)
    items = tuple(
        HomeworkReviewQueueItem(
            submission_id=submission.id,
            assignment_slug=submission.assignment.slug,
            assignment_title=submission.assignment.title,
            author_identifier=submission.author_identifier,
            attempt_number=submission.attempt_number,
            submission_state=str(submission.submission_state),
            submitted_at=submission.submitted_at,
            author_user_id=(
                users_by_author_identifier[submission.author_identifier].id
                if submission.author_identifier in users_by_author_identifier
                else None
            ),
            author_display_name=(
                (
                    users_by_author_identifier[submission.author_identifier].display_name
                    or users_by_author_identifier[submission.author_identifier].get_username()
                )
                if submission.author_identifier in users_by_author_identifier
                else ""
            ),
            author_contacts=(
                _build_learner_contact_snapshot(users_by_author_identifier[submission.author_identifier])
                if submission.author_identifier in users_by_author_identifier
                else None
            ),
            answer_preview=_submission_text_preview(submission),
        )
        for submission in submissions
    )
    return HomeworkReviewQueueSnapshot(pending_count=len(items), items=items)


@transaction.atomic
def review_homework_submission(
    *,
    submission_id: int,
    reviewer_user_id: int,
    decision: str,
    feedback: str = "",
    score: Decimal | None = None,
) -> HomeworkReviewDecisionResult:
    require_operator_permissions(user_id=reviewer_user_id, action="проверять домашние задания")
    submission = (
        HomeworkSubmission.objects.select_for_update()
        .select_related("assignment")
        .get(id=submission_id)
    )
    if decision not in HomeworkReview.ReviewDecision.values:
        raise ValueError(f"Неподдерживаемое решение по домашнему заданию: {decision!r}")

    review, _created = HomeworkReview.objects.update_or_create(
        submission=submission,
        reviewer_identifier=str(reviewer_user_id),
        defaults={
            "decision": decision,
            "score": score,
            "feedback": feedback,
            "rubric_snapshot": {"source": "operator_stage7"},
            "reviewed_at": timezone.now(),
        },
    )
    if decision == HomeworkReview.ReviewDecision.CHANGES_REQUESTED:
        submission.submission_state = HomeworkSubmission.SubmissionState.RETURNED
    else:
        submission.submission_state = HomeworkSubmission.SubmissionState.REVIEWED
    submission.save(update_fields=["submission_state", "updated_at"])

    notification_job = enqueue_notification(
        channel="system",
        template_key="homework.reviewed",
        payload={
            "submission_id": submission.id,
            "assignment_slug": submission.assignment.slug,
            "author_identifier": submission.author_identifier,
            "decision": decision,
        },
    )
    audit_log = record_operator_action(
        action="operator.homework.review",
        actor_user_id=reviewer_user_id,
        target_type="homework.HomeworkSubmission",
        target_key=str(submission.id),
        message=f"Домашнее задание проверено с решением {decision}.",
        payload={
            "review_id": review.id,
            "assignment_slug": submission.assignment.slug,
            "decision": decision,
            "score": str(score) if score is not None else "",
        },
    )
    return HomeworkReviewDecisionResult(
        submission_id=submission.id,
        review_id=review.id,
        submission_state=str(submission.submission_state),
        decision=str(review.decision),
        audit_log_id=audit_log.id,
        notification_job_id=notification_job.id,
    )


@transaction.atomic
def enqueue_learner_access_link(
    *,
    learner_user_id: int,
    actor_user_id: int,
    reason: str,
) -> NotificationJob:
    require_operator_permissions(user_id=actor_user_id, action="отправить ссылку доступа ученику")
    reason = reason.strip()
    if not reason:
        raise ValueError("Для повторной отправки ссылки доступа нужна причина.")

    user = get_user_model().objects.only("id", "username").get(id=learner_user_id)
    notification_job = enqueue_notification(
        channel="system",
        template_key="learner.access_link",
        user_id=user.id,
        payload={
            "reason": reason,
            "requested_by_user_id": actor_user_id,
            "path": "/learn/",
        },
    )
    record_operator_action(
        action="operator.learner.resend_access_link",
        actor_user_id=actor_user_id,
        target_type="accounts.User",
        target_key=str(user.id),
        message=reason,
        payload={"notification_job_id": notification_job.id},
    )
    return notification_job


def get_operator_dashboard_metrics() -> OperatorDashboardMetrics:
    now = timezone.now()
    active_paid_access_grants = AccessGrant.objects.filter(
        _access_window(now),
        status=AccessGrant.Status.ACTIVE,
        revoked_at__isnull=True,
    ).count()
    active_preview_access_grants = PreviewAccessGrant.objects.filter(
        _access_window(now),
        status=PreviewAccessGrant.Status.ACTIVE,
        revoked_at__isnull=True,
    ).count()

    operator_users = (
        UserRole.objects.filter(role__code__in=OPERATOR_ROLE_CODES)
        .values("user_id")
        .distinct()
        .count()
    )
    learner_users = (
        UserRole.objects.filter(role__code__in=LEARNER_ROLE_CODES)
        .values("user_id")
        .distinct()
        .count()
    )
    pending_homework_reviews = _pending_homework_submission_queryset().count()

    return OperatorDashboardMetrics(
        total_users=get_user_model().objects.count(),
        operator_users=operator_users,
        learner_users=learner_users,
        paid_orders=Order.objects.filter(status=Order.Status.PAID).count(),
        pending_orders=Order.objects.filter(status="pending").count(),
        active_paid_access_grants=active_paid_access_grants,
        active_preview_access_grants=active_preview_access_grants,
        published_courses=Course.objects.filter(publication_status="published").count(),
        draft_courses=Course.objects.filter(publication_status="draft").count(),
        published_lessons=Lesson.objects.filter(publication_status="published").count(),
        completed_lessons=ProgressRecord.objects.filter(status="completed").count(),
        pending_homework_reviews=pending_homework_reviews,
    )
