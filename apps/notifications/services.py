from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from .models import NotificationJob
from .providers import (
    NotificationDispatchError,
    NotificationProviderRegistry,
    PermanentNotificationError,
    StubNotificationProvider,
)
from .templates import NotificationTemplateKey, render_notification

__all__ = [
    "DispatchNotificationsResult",
    "RetryPolicy",
    "dispatch_notification_job",
    "dispatch_pending_notifications",
    "enqueue_homework_reviewed_notification",
    "enqueue_lesson_completed_notification",
    "enqueue_lesson_zero_entry_notification",
    "enqueue_notification",
    "enqueue_paid_access_notification",
    "list_pending_notifications",
]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    retry_delays: tuple[timedelta, ...] = (
        timedelta(minutes=5),
        timedelta(minutes=30),
        timedelta(hours=2),
    )

    def delay_for_attempt(self, attempt_number: int) -> timedelta:
        if attempt_number <= 0:
            return timedelta(0)
        index = min(attempt_number - 1, len(self.retry_delays) - 1)
        return self.retry_delays[index]


@dataclass(frozen=True, slots=True)
class DispatchNotificationsResult:
    processed_job_ids: tuple[int, ...]
    sent_job_ids: tuple[int, ...]
    retried_job_ids: tuple[int, ...]
    dead_letter_job_ids: tuple[int, ...]


DEFAULT_RETRY_POLICY = RetryPolicy()
SYSTEM_CHANNEL = "system"
EMAIL_CHANNEL = "email"
TELEGRAM_CHANNEL = "telegram"


@transaction.atomic
def enqueue_notification(
    *,
    channel: str,
    template_key: str,
    user_id: int | None = None,
    payload: Mapping[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> NotificationJob:
    normalized_dedupe_key = _normalize_dedupe_key(dedupe_key)
    defaults = {
        "user_id": user_id,
        "channel": channel,
        "template_key": template_key,
        "payload": dict(payload or {}),
        "scheduled_at": scheduled_at or timezone.now(),
    }
    if normalized_dedupe_key is None:
        return NotificationJob.objects.create(**defaults)

    job, _created = NotificationJob.objects.get_or_create(
        dedupe_key=normalized_dedupe_key,
        defaults=defaults,
    )
    return job


def enqueue_lesson_zero_entry_notification(
    *,
    user_id: int | None,
    course_slug: str,
    lesson_slug: str = "lesson-0",
    channel: str = SYSTEM_CHANNEL,
    payload: Mapping[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> NotificationJob:
    base_payload = {
        "course_slug": course_slug,
        "lesson_slug": lesson_slug,
    }
    base_payload.update(dict(payload or {}))
    return enqueue_notification(
        channel=channel,
        template_key=NotificationTemplateKey.LESSON0_OPENED,
        user_id=user_id,
        payload=base_payload,
        scheduled_at=scheduled_at,
        dedupe_key=dedupe_key or f"lesson0:{user_id}:{course_slug}:{lesson_slug}",
    )


def enqueue_paid_access_notification(
    *,
    user_id: int | None,
    access_path: str = "/learn/",
    order_number: str = "",
    channel: str = SYSTEM_CHANNEL,
    payload: Mapping[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> NotificationJob:
    base_payload = {
        "access_path": access_path,
        "order_number": order_number,
    }
    base_payload.update(dict(payload or {}))
    dedupe_parts = [str(user_id), access_path, order_number or "no-order"]
    return enqueue_notification(
        channel=channel,
        template_key=NotificationTemplateKey.PAID_ACCESS_GRANTED,
        user_id=user_id,
        payload=base_payload,
        scheduled_at=scheduled_at,
        dedupe_key=dedupe_key or f"paid-access:{':'.join(dedupe_parts)}",
    )


def enqueue_lesson_completed_notification(
    *,
    user_id: int | None,
    course_slug: str,
    lesson_slug: str,
    channel: str = SYSTEM_CHANNEL,
    payload: Mapping[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> NotificationJob:
    base_payload = {
        "course_slug": course_slug,
        "lesson_slug": lesson_slug,
    }
    base_payload.update(dict(payload or {}))
    return enqueue_notification(
        channel=channel,
        template_key=NotificationTemplateKey.LESSON_COMPLETED,
        user_id=user_id,
        payload=base_payload,
        scheduled_at=scheduled_at,
        dedupe_key=dedupe_key or f"lesson-completed:{user_id}:{course_slug}:{lesson_slug}",
    )


def enqueue_homework_reviewed_notification(
    *,
    user_id: int | None,
    submission_id: int,
    assignment_slug: str,
    decision: str,
    author_identifier: str = "",
    channel: str = SYSTEM_CHANNEL,
    payload: Mapping[str, Any] | None = None,
    scheduled_at: datetime | None = None,
    dedupe_key: str | None = None,
) -> NotificationJob:
    base_payload = {
        "submission_id": submission_id,
        "assignment_slug": assignment_slug,
        "author_identifier": author_identifier,
        "decision": decision,
    }
    base_payload.update(dict(payload or {}))
    return enqueue_notification(
        channel=channel,
        template_key=NotificationTemplateKey.HOMEWORK_REVIEWED,
        user_id=user_id,
        payload=base_payload,
        scheduled_at=scheduled_at,
        dedupe_key=dedupe_key or f"homework-reviewed:{submission_id}:{decision}",
    )


def list_pending_notifications(*, now: datetime | None = None) -> QuerySet[NotificationJob]:
    return NotificationJob.objects.filter(
        status=NotificationJob.Status.PENDING,
        scheduled_at__lte=now or timezone.now(),
    ).order_by(*NotificationJob._meta.ordering)


def dispatch_pending_notifications(
    *,
    provider_registry: NotificationProviderRegistry | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    now: datetime | None = None,
    limit: int | None = None,
) -> DispatchNotificationsResult:
    pending_jobs = list_pending_notifications(now=now)
    if limit is not None:
        pending_jobs = pending_jobs[:limit]
    pending_job_ids = list(pending_jobs.values_list("id", flat=True))
    sent_job_ids: list[int] = []
    retried_job_ids: list[int] = []
    dead_letter_job_ids: list[int] = []

    for job_id in pending_job_ids:
        job = dispatch_notification_job(
            job_id=job_id,
            provider_registry=provider_registry,
            retry_policy=retry_policy,
            now=now,
        )
        if job.status == NotificationJob.Status.SENT:
            sent_job_ids.append(job.id)
        elif job.status == NotificationJob.Status.DEAD_LETTER:
            dead_letter_job_ids.append(job.id)
        elif job.status == NotificationJob.Status.PENDING and job.attempts > 0:
            retried_job_ids.append(job.id)

    return DispatchNotificationsResult(
        processed_job_ids=tuple(pending_job_ids),
        sent_job_ids=tuple(sent_job_ids),
        retried_job_ids=tuple(retried_job_ids),
        dead_letter_job_ids=tuple(dead_letter_job_ids),
    )


@transaction.atomic
def dispatch_notification_job(
    *,
    job_id: int,
    provider_registry: NotificationProviderRegistry | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    now: datetime | None = None,
) -> NotificationJob:
    current_time = now or timezone.now()
    job = NotificationJob.objects.select_for_update().get(id=job_id)
    if job.status != NotificationJob.Status.PENDING or job.scheduled_at > current_time:
        return job

    registry = provider_registry or _build_default_provider_registry()
    try:
        provider = registry.resolve(job.channel)
        rendered = render_notification(template_key=job.template_key, payload=job.payload)
        provider.send(job=job, message=rendered)
    except PermanentNotificationError as exc:
        return _mark_dead_letter(job=job, error=str(exc))
    except NotificationDispatchError as exc:
        return _mark_retry_or_dead_letter(
            job=job,
            error=str(exc),
            retry_policy=retry_policy,
            current_time=current_time,
        )
    except Exception as exc:
        return _mark_retry_or_dead_letter(
            job=job,
            error=str(exc),
            retry_policy=retry_policy,
            current_time=current_time,
        )

    job.status = NotificationJob.Status.SENT
    job.attempts += 1
    job.sent_at = current_time
    job.last_error = ""
    job.save(update_fields=["status", "attempts", "sent_at", "last_error", "updated_at"])
    return job


def _build_default_provider_registry() -> NotificationProviderRegistry:
    return NotificationProviderRegistry(
        providers=[
            StubNotificationProvider(channel=TELEGRAM_CHANNEL),
            StubNotificationProvider(channel=EMAIL_CHANNEL),
            StubNotificationProvider(channel=SYSTEM_CHANNEL),
        ]
    )


def _mark_retry_or_dead_letter(
    *,
    job: NotificationJob,
    error: str,
    retry_policy: RetryPolicy,
    current_time: datetime,
) -> NotificationJob:
    job.attempts += 1
    job.last_error = error
    if job.attempts >= retry_policy.max_attempts:
        job.status = NotificationJob.Status.DEAD_LETTER
        job.save(update_fields=["attempts", "last_error", "status", "updated_at"])
        return job

    job.status = NotificationJob.Status.PENDING
    job.scheduled_at = current_time + retry_policy.delay_for_attempt(job.attempts)
    job.save(update_fields=["attempts", "last_error", "scheduled_at", "status", "updated_at"])
    return job


def _mark_dead_letter(*, job: NotificationJob, error: str) -> NotificationJob:
    job.attempts += 1
    job.status = NotificationJob.Status.DEAD_LETTER
    job.last_error = error
    job.save(update_fields=["attempts", "status", "last_error", "updated_at"])
    return job


def _normalize_dedupe_key(dedupe_key: str | None) -> str | None:
    if dedupe_key is None:
        return None
    normalized = dedupe_key.strip()
    return normalized or None
