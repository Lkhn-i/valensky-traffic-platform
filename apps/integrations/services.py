from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from .models import ExternalEvent, IntegrationOutboxEvent


@transaction.atomic
def record_external_event(
    *,
    source: str,
    event_type: str,
    idempotency_key: str,
    payload: Mapping[str, Any] | None = None,
) -> tuple[ExternalEvent, bool]:
    event, created = ExternalEvent.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "source": source,
            "event_type": event_type,
            "payload": dict(payload or {}),
        },
    )
    return event, created


def mark_event_processed(*, event_id: int) -> ExternalEvent:
    event = ExternalEvent.objects.get(id=event_id)
    event.processing_status = ExternalEvent.ProcessingStatus.PROCESSED
    event.processed_at = timezone.now()
    event.error = ""
    event.save(update_fields=["processing_status", "processed_at", "error"])
    return event


def list_unprocessed_events() -> QuerySet[ExternalEvent]:
    return ExternalEvent.objects.filter(
        processing_status=ExternalEvent.ProcessingStatus.RECEIVED,
    ).order_by(*ExternalEvent._meta.ordering)


@transaction.atomic
def enqueue_bot_outbox_event(
    *,
    event_type: str,
    idempotency_key: str,
    payload: Mapping[str, Any] | None = None,
    user_id: int | None = None,
    notification_job_id: int | None = None,
) -> tuple[IntegrationOutboxEvent, bool]:
    event, created = IntegrationOutboxEvent.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "destination": IntegrationOutboxEvent.Destination.TELEGRAM_BOT,
            "event_type": event_type,
            "user_id": user_id,
            "notification_job_id": notification_job_id,
            "payload": dict(payload or {}),
        },
    )
    return event, created


def enqueue_bot_outbox_from_notification(
    *,
    notification_job_id: int,
    template_key: str,
    idempotency_key: str,
    payload: Mapping[str, Any] | None = None,
    user_id: int | None = None,
    event_type: str = "notification.queued",
) -> tuple[IntegrationOutboxEvent, bool]:
    outbox_payload = {
        "notification_job_id": notification_job_id,
        "template_key": template_key,
        **dict(payload or {}),
    }
    return enqueue_bot_outbox_event(
        event_type=event_type,
        idempotency_key=idempotency_key,
        payload=outbox_payload,
        user_id=user_id,
        notification_job_id=notification_job_id,
    )


def list_pending_bot_outbox_events() -> QuerySet[IntegrationOutboxEvent]:
    return IntegrationOutboxEvent.objects.filter(
        destination=IntegrationOutboxEvent.Destination.TELEGRAM_BOT,
        processing_status=IntegrationOutboxEvent.ProcessingStatus.PENDING,
        scheduled_at__lte=timezone.now(),
    ).order_by(*IntegrationOutboxEvent._meta.ordering)


def mark_outbox_event_sent(*, event_id: int) -> IntegrationOutboxEvent:
    event = IntegrationOutboxEvent.objects.get(id=event_id)
    event.processing_status = IntegrationOutboxEvent.ProcessingStatus.SENT
    event.sent_at = timezone.now()
    event.last_error = ""
    event.save(update_fields=["processing_status", "sent_at", "last_error", "updated_at"])
    return event


def mark_outbox_event_failed(
    *,
    event_id: int,
    error: str,
    dead_letter: bool = False,
) -> IntegrationOutboxEvent:
    event = IntegrationOutboxEvent.objects.get(id=event_id)
    event.attempts += 1
    event.last_error = error
    event.processing_status = (
        IntegrationOutboxEvent.ProcessingStatus.DEAD_LETTER
        if dead_letter
        else IntegrationOutboxEvent.ProcessingStatus.FAILED
    )
    event.save(update_fields=["attempts", "last_error", "processing_status", "updated_at"])
    return event
