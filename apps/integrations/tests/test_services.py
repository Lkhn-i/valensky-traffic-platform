import pytest

from apps.access_control.models import AccessGrant
from apps.integrations.models import IntegrationOutboxEvent
from apps.integrations.services import (
    enqueue_bot_outbox_event,
    list_pending_bot_outbox_events,
    mark_event_processed,
    mark_outbox_event_failed,
    mark_outbox_event_sent,
    record_external_event,
)
from apps.learning_state.models import ProgressRecord


@pytest.mark.django_db
def test_external_event_idempotency_key_is_replay_safe() -> None:
    first_event, first_created = record_external_event(
        source="payment_provider",
        event_type="robokassa.placeholder",
        idempotency_key="payment:event:1",
        payload={"status": "paid"},
    )
    replay_event, replay_created = record_external_event(
        source="payment_provider",
        event_type="robokassa.placeholder",
        idempotency_key="payment:event:1",
        payload={"status": "paid"},
    )

    processed_event = mark_event_processed(event_id=first_event.id)

    assert first_created is True
    assert replay_created is False
    assert replay_event.id == first_event.id
    assert processed_event.processing_status == "processed"


@pytest.mark.django_db
def test_bot_outbox_event_idempotency_key_is_replay_safe() -> None:
    first_event, first_created = enqueue_bot_outbox_event(
        event_type="lesson0.entry_link",
        idempotency_key="bot:lesson0:1",
        payload={"path": "/learn/"},
    )
    replay_event, replay_created = enqueue_bot_outbox_event(
        event_type="lesson0.entry_link",
        idempotency_key="bot:lesson0:1",
        payload={"path": "/another/"},
    )

    assert first_created is True
    assert replay_created is False
    assert replay_event.id == first_event.id
    assert replay_event.payload == {"path": "/learn/"}
    assert list(list_pending_bot_outbox_events()) == [first_event]


@pytest.mark.django_db
def test_bot_outbox_sent_and_dead_letter_state_transitions() -> None:
    sent_event, _created = enqueue_bot_outbox_event(
        event_type="paid_access.granted",
        idempotency_key="bot:paid:1",
    )
    failed_event, _created = enqueue_bot_outbox_event(
        event_type="lesson.completed",
        idempotency_key="bot:lesson-completed:1",
    )

    sent_event = mark_outbox_event_sent(event_id=sent_event.id)
    failed_event = mark_outbox_event_failed(
        event_id=failed_event.id,
        error="telegram timeout",
        dead_letter=True,
    )

    assert sent_event.processing_status == IntegrationOutboxEvent.ProcessingStatus.SENT
    assert sent_event.sent_at is not None
    assert failed_event.processing_status == IntegrationOutboxEvent.ProcessingStatus.DEAD_LETTER
    assert failed_event.attempts == 1
    assert failed_event.last_error == "telegram timeout"


@pytest.mark.django_db
def test_telegram_inbound_event_does_not_change_canonical_lms_state() -> None:
    record_external_event(
        source="telegram_bot",
        event_type="paid_access.requested",
        idempotency_key="telegram:access-request:1",
        payload={"user_id": 100, "course_id": 200},
    )

    assert AccessGrant.objects.count() == 0
    assert ProgressRecord.objects.count() == 0
