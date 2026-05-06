from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.notifications.models import NotificationJob
from apps.notifications.providers import (
    NotificationProviderRegistry,
    PermanentNotificationError,
    RetryableNotificationError,
    StubNotificationProvider,
)
from apps.notifications.services import (
    DispatchNotificationsResult,
    RetryPolicy,
    dispatch_notification_job,
    dispatch_pending_notifications,
    enqueue_homework_reviewed_notification,
    enqueue_lesson_completed_notification,
    enqueue_lesson_zero_entry_notification,
    enqueue_notification,
    enqueue_paid_access_notification,
    list_pending_notifications,
)
from apps.notifications.templates import NotificationTemplateKey


def create_user(*, username: str):
    return get_user_model().objects.create_user(username=username, password="pass")


@pytest.mark.django_db
def test_enqueue_notification_creates_pending_job() -> None:
    job = enqueue_notification(
        channel="telegram",
        template_key="lesson0.opened",
        payload={"lesson": "lesson-0"},
    )

    assert job.status == "pending"
    assert list(list_pending_notifications()) == [job]


@pytest.mark.django_db
def test_enqueue_notification_dedupes_by_key() -> None:
    first_job = enqueue_notification(
        channel=NotificationJob.Channel.SYSTEM,
        template_key=NotificationTemplateKey.LESSON0_OPENED,
        payload={"lesson_slug": "lesson-0"},
        dedupe_key="lesson0:1",
    )
    second_job = enqueue_notification(
        channel=NotificationJob.Channel.SYSTEM,
        template_key=NotificationTemplateKey.LESSON0_OPENED,
        payload={"lesson_slug": "lesson-0-replayed"},
        dedupe_key="lesson0:1",
    )

    assert first_job.id == second_job.id
    assert NotificationJob.objects.count() == 1
    assert NotificationJob.objects.get().payload == {"lesson_slug": "lesson-0"}


@pytest.mark.django_db
def test_specialized_enqueue_helpers_create_expected_templates() -> None:
    user = create_user(username="notify-helper")
    lesson0_job = enqueue_lesson_zero_entry_notification(user_id=user.id, course_slug="guts-course")
    paid_access_job = enqueue_paid_access_notification(
        user_id=user.id,
        access_path="/learn/guts/",
        order_number="A-42",
    )
    lesson_completed_job = enqueue_lesson_completed_notification(
        user_id=user.id,
        course_slug="guts-course",
        lesson_slug="lesson-1",
    )
    homework_job = enqueue_homework_reviewed_notification(
        user_id=user.id,
        submission_id=12,
        assignment_slug="intro-homework",
        decision="approved",
        author_identifier="student-7",
    )

    assert lesson0_job.template_key == NotificationTemplateKey.LESSON0_OPENED
    assert lesson0_job.dedupe_key == f"lesson0:{user.id}:guts-course:lesson-0"
    assert paid_access_job.template_key == NotificationTemplateKey.PAID_ACCESS_GRANTED
    assert paid_access_job.payload["access_path"] == "/learn/guts/"
    assert lesson_completed_job.template_key == NotificationTemplateKey.LESSON_COMPLETED
    assert homework_job.template_key == NotificationTemplateKey.HOMEWORK_REVIEWED
    assert homework_job.payload["author_identifier"] == "student-7"


@pytest.mark.django_db
def test_dispatch_notification_job_marks_sent_with_stub_provider() -> None:
    user = create_user(username="notify-sent")
    provider = StubNotificationProvider(channel="system")
    registry = NotificationProviderRegistry([provider])
    job = enqueue_homework_reviewed_notification(
        user_id=user.id,
        submission_id=22,
        assignment_slug="hw-1",
        decision="approved",
    )
    now = timezone.now()

    dispatched_job = dispatch_notification_job(
        job_id=job.id,
        provider_registry=registry,
        now=now,
    )

    assert dispatched_job.status == NotificationJob.Status.SENT
    assert dispatched_job.sent_at == now
    assert dispatched_job.attempts == 1
    assert provider.deliveries == [(job.id, NotificationTemplateKey.HOMEWORK_REVIEWED)]


@pytest.mark.django_db
def test_dispatch_notification_job_retries_retryable_failures() -> None:
    now = timezone.now()
    user = create_user(username="notify-retry")
    provider = StubNotificationProvider(
        channel="system",
        outcomes=[RetryableNotificationError("temporary outage")],
    )
    registry = NotificationProviderRegistry([provider])
    job = enqueue_paid_access_notification(
        user_id=user.id,
        access_path="/learn/",
        scheduled_at=now,
    )
    retry_policy = RetryPolicy(max_attempts=3, retry_delays=(timedelta(minutes=15),))

    dispatched_job = dispatch_notification_job(
        job_id=job.id,
        provider_registry=registry,
        retry_policy=retry_policy,
        now=now,
    )

    assert dispatched_job.status == NotificationJob.Status.PENDING
    assert dispatched_job.attempts == 1
    assert dispatched_job.last_error == "temporary outage"
    assert dispatched_job.scheduled_at == now + timedelta(minutes=15)


@pytest.mark.django_db
def test_dispatch_notification_job_moves_permanent_failures_to_dead_letter() -> None:
    user = create_user(username="notify-dead")
    provider = StubNotificationProvider(
        channel="system",
        outcomes=[PermanentNotificationError("template payload is invalid")],
    )
    registry = NotificationProviderRegistry([provider])
    job = enqueue_lesson_completed_notification(
        user_id=user.id,
        course_slug="guts-course",
        lesson_slug="lesson-2",
    )

    dispatched_job = dispatch_notification_job(
        job_id=job.id,
        provider_registry=registry,
    )

    assert dispatched_job.status == NotificationJob.Status.DEAD_LETTER
    assert dispatched_job.attempts == 1
    assert dispatched_job.last_error == "template payload is invalid"


@pytest.mark.django_db
def test_dispatch_pending_notifications_returns_batch_result() -> None:
    now = timezone.now()
    due_user = create_user(username="notify-due")
    future_user = create_user(username="notify-future")
    provider = StubNotificationProvider(channel="system")
    registry = NotificationProviderRegistry([provider])
    due_job = enqueue_lesson_zero_entry_notification(
        user_id=due_user.id,
        course_slug="guts-course",
        scheduled_at=now,
    )
    future_job = enqueue_lesson_zero_entry_notification(
        user_id=future_user.id,
        course_slug="guts-course",
        scheduled_at=now + timedelta(hours=1),
    )

    result = dispatch_pending_notifications(provider_registry=registry, now=now)

    due_job.refresh_from_db()
    future_job.refresh_from_db()
    assert result == DispatchNotificationsResult(
        processed_job_ids=(due_job.id,),
        sent_job_ids=(due_job.id,),
        retried_job_ids=(),
        dead_letter_job_ids=(),
    )
    assert due_job.status == NotificationJob.Status.SENT
    assert future_job.status == NotificationJob.Status.PENDING
