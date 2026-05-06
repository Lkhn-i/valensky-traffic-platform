from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.access_control.models import Tariff
from apps.access_control.services import check_access, grant_paid_access, grant_preview_access
from apps.accounts.services import get_or_create_lead_from_diagnostic
from apps.curriculum.models import Course, Lesson, Module
from apps.learning_state.models import ProgressRecord
from apps.learning_state.services import (
    complete_lesson,
    get_progress_for_lesson,
    list_progress_for_course,
    update_progress,
)


def _course_tree() -> tuple[Course, Module, Lesson, Lesson]:
    course = Course.objects.create(
        slug="gatsa-sales",
        title="Gatsa Sales",
        publication_status=Course.PublicationStatus.PUBLISHED,
    )
    module = Module.objects.create(
        course=course,
        slug="start",
        title="Start",
        publication_status=Module.PublicationStatus.PUBLISHED,
        position=0,
    )
    lesson0 = Lesson.objects.create(
        module=module,
        slug="lesson-0",
        title="Урок 0",
        publication_status=Lesson.PublicationStatus.PUBLISHED,
        position=0,
    )
    lesson1 = Lesson.objects.create(
        module=module,
        slug="lesson-1",
        title="Урок 1",
        publication_status=Lesson.PublicationStatus.PUBLISHED,
        position=1,
    )
    return course, module, lesson0, lesson1


@pytest.mark.django_db
def test_progress_helpers_cover_open_complete_and_missing_course_entries() -> None:
    user = get_user_model().objects.create_user(username="student")
    course, _module, lesson0, lesson1 = _course_tree()

    initial_snapshot = get_progress_for_lesson(user.id, lesson0.id)

    opened_record = update_progress(
        user_id=user.id,
        lesson_id=lesson0.id,
        status=ProgressRecord.Status.OPENED,
        source="lesson_page",
    )
    completed_record = complete_lesson(user.id, lesson0.id)

    lesson_snapshot = get_progress_for_lesson(user.id, lesson0.id)
    course_progress = list_progress_for_course(user_id=user.id, course_id=course.id)

    assert initial_snapshot.status == ProgressRecord.Status.NOT_STARTED
    assert initial_snapshot.has_record is False
    assert opened_record.id == completed_record.id
    assert completed_record.status == ProgressRecord.Status.COMPLETED
    assert completed_record.first_opened_at == opened_record.first_opened_at
    assert completed_record.completed_at is not None
    assert lesson_snapshot.status == ProgressRecord.Status.COMPLETED
    assert lesson_snapshot.has_record is True
    assert lesson_snapshot.completed_at == completed_record.completed_at
    assert [snapshot.lesson_id for snapshot in course_progress] == [lesson0.id, lesson1.id]
    assert course_progress[0].status == ProgressRecord.Status.COMPLETED
    assert course_progress[0].has_record is True
    assert course_progress[1].status == ProgressRecord.Status.NOT_STARTED
    assert course_progress[1].has_record is False


@pytest.mark.django_db
def test_complete_lesson_is_idempotent() -> None:
    user = get_user_model().objects.create_user(username="student")
    _course, _module, lesson0, _lesson1 = _course_tree()

    first_record = complete_lesson(user.id, lesson0.id)
    second_record = complete_lesson(user.id, lesson0.id)

    assert first_record.id == second_record.id
    assert ProgressRecord.objects.count() == 1
    assert second_record.completed_at == first_record.completed_at
    assert second_record.first_opened_at == first_record.first_opened_at
    assert second_record.last_opened_at == first_record.last_opened_at
    assert second_record.status == ProgressRecord.Status.COMPLETED


@pytest.mark.django_db
def test_lesson0_progress_survives_preview_to_paid_access_change() -> None:
    course, _module, lesson0, _lesson1 = _course_tree()
    lead_profile, _created = get_or_create_lead_from_diagnostic(
        external_session_id="diag-session-1",
        source="diagnostic_site",
    )

    grant_preview_access(
        lead_profile_id=lead_profile.id,
        course_id=course.id,
        lesson_id=lesson0.id,
        expires_at=timezone.now() + timedelta(days=1),
    )
    opened_record = update_progress(
        user_id=lead_profile.user_id,
        lesson_id=lesson0.id,
        status=ProgressRecord.Status.OPENED,
        source="lesson_page",
    )
    preview_decision = check_access(user_id=lead_profile.user_id, lesson_id=lesson0.id)

    tariff = Tariff.objects.create(code=Tariff.Code.BASE, course=course, title="Базовый")
    grant_paid_access(
        user_id=lead_profile.user_id,
        course_id=course.id,
        tariff_id=tariff.id,
        source="payment",
        source_reference="invoice-1",
    )
    paid_decision = check_access(user_id=lead_profile.user_id, lesson_id=lesson0.id)
    snapshot = get_progress_for_lesson(lead_profile.user_id, lesson0.id)

    assert preview_decision.allowed is True
    assert preview_decision.reason == "lesson0_preview_grant"
    assert paid_decision.allowed is True
    assert paid_decision.reason == "paid_access_grant"
    assert ProgressRecord.objects.count() == 1
    assert snapshot.status == ProgressRecord.Status.OPENED
    assert snapshot.has_record is True
    assert snapshot.first_opened_at == opened_record.first_opened_at
    assert snapshot.last_opened_at == opened_record.last_opened_at
