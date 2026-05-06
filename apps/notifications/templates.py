from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .providers import PermanentNotificationError


class NotificationTemplateKey:
    LESSON0_OPENED = "lesson0.opened"
    PAID_ACCESS_GRANTED = "paid.access_granted"
    LESSON_COMPLETED = "lesson.completed"
    HOMEWORK_REVIEWED = "homework.reviewed"
    LEARNER_ACCESS_LINK = "learner.access_link"


@dataclass(frozen=True, slots=True)
class RenderedNotification:
    template_key: str
    subject: str
    body: str
    payload: Mapping[str, Any]


def render_notification(*, template_key: str, payload: Mapping[str, Any]) -> RenderedNotification:
    renderer = _TEMPLATE_RENDERERS.get(template_key)
    if renderer is None:
        raise PermanentNotificationError(f"Неизвестный шаблон уведомления {template_key!r}.")
    return renderer(payload)


def _render_lesson0_opened(payload: Mapping[str, Any]) -> RenderedNotification:
    lesson_slug = str(payload.get("lesson_slug") or "lesson-0")
    course_slug = str(payload.get("course_slug") or "course")
    return RenderedNotification(
        template_key=NotificationTemplateKey.LESSON0_OPENED,
        subject="Урок 0 открыт",
        body=f"В курсе {course_slug} открыт урок {lesson_slug}.",
        payload=dict(payload),
    )


def _render_paid_access_granted(payload: Mapping[str, Any]) -> RenderedNotification:
    access_path = str(payload.get("access_path") or "/learn/")
    order_number = str(payload.get("order_number") or "")
    order_suffix = f" Заказ {order_number}." if order_number else ""
    return RenderedNotification(
        template_key=NotificationTemplateKey.PAID_ACCESS_GRANTED,
        subject="Платный доступ открыт",
        body=f"Доступ к обучению готов: {access_path}.{order_suffix}".strip(),
        payload=dict(payload),
    )


def _render_lesson_completed(payload: Mapping[str, Any]) -> RenderedNotification:
    lesson_slug = str(payload.get("lesson_slug") or "lesson")
    course_slug = str(payload.get("course_slug") or "course")
    return RenderedNotification(
        template_key=NotificationTemplateKey.LESSON_COMPLETED,
        subject="Урок завершён",
        body=f"Ученик завершил {course_slug}/{lesson_slug}.",
        payload=dict(payload),
    )


def _render_homework_reviewed(payload: Mapping[str, Any]) -> RenderedNotification:
    assignment_slug = str(payload.get("assignment_slug") or "assignment")
    decision = str(payload.get("decision") or "проверено")
    submission_id = str(payload.get("submission_id") or "")
    suffix = f" Отправка {submission_id}." if submission_id else ""
    return RenderedNotification(
        template_key=NotificationTemplateKey.HOMEWORK_REVIEWED,
        subject="Домашнее задание проверено",
        body=f"Домашнее задание {assignment_slug}: {decision}.{suffix}".strip(),
        payload=dict(payload),
    )


def _render_learner_access_link(payload: Mapping[str, Any]) -> RenderedNotification:
    access_path = str(payload.get("path") or "/learn/")
    reason = str(payload.get("reason") or "Запрошена ссылка доступа.")
    return RenderedNotification(
        template_key=NotificationTemplateKey.LEARNER_ACCESS_LINK,
        subject="Ссылка доступа к обучению",
        body=f"{reason} Перейдите: {access_path}.",
        payload=dict(payload),
    )


_TEMPLATE_RENDERERS = {
    NotificationTemplateKey.LESSON0_OPENED: _render_lesson0_opened,
    NotificationTemplateKey.PAID_ACCESS_GRANTED: _render_paid_access_granted,
    NotificationTemplateKey.LESSON_COMPLETED: _render_lesson_completed,
    NotificationTemplateKey.HOMEWORK_REVIEWED: _render_homework_reviewed,
    NotificationTemplateKey.LEARNER_ACCESS_LINK: _render_learner_access_link,
}
