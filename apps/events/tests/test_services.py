import pytest

from apps.events.services import (
    ORMAnalyticsEventService,
    ORMAuditLogService,
    StubAnalyticsEventService,
    StubAuditLogService,
)


@pytest.mark.django_db
def test_event_services_record_analytics_and_audit_entries() -> None:
    analytics_service = ORMAnalyticsEventService()
    audit_service = ORMAuditLogService()

    event = analytics_service.record_event(
        name="lesson_opened",
        source_app="curriculum",
        actor_identifier="student-1",
        object_type="lesson",
        object_key="lesson-1",
        properties={"position": 1},
    )
    log = audit_service.record_log(
        action="homework.reviewed",
        result="success",
        actor_identifier="mentor-1",
        target_type="submission",
        target_key="submission-1",
        message="Review completed",
        payload={"score": 100},
    )

    assert event.pk is not None
    assert log.pk is not None
    assert list(analytics_service.list_events(source_app="curriculum")) == [event]
    assert list(audit_service.list_logs(result="success")) == [log]


def test_event_stub_services_return_unsaved_entries() -> None:
    analytics_service = StubAnalyticsEventService()
    audit_service = StubAuditLogService()

    event = analytics_service.record_event(name="stub", source_app="events")
    log = audit_service.record_log(action="stub")

    assert event.pk is None
    assert log.pk is None
