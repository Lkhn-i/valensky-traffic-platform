from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.curriculum.models import Lesson

from .models import ProgressRecord

__all__ = [
    "LessonProgressSnapshot",
    "complete_lesson",
    "get_progress_for_lesson",
    "list_progress_for_course",
    "list_progress_for_user",
    "update_progress",
]


@dataclass(frozen=True, slots=True)
class LessonProgressSnapshot:
    progress_id: int | None
    user_id: int
    course_id: int
    module_id: int
    module_position: int
    lesson_id: int
    lesson_position: int
    status: str
    first_opened_at: datetime | None
    last_opened_at: datetime | None
    completed_at: datetime | None
    source: str
    metadata: dict[str, Any]
    has_record: bool

    @property
    def is_completed(self) -> bool:
        return self.status == ProgressRecord.Status.COMPLETED

    @property
    def is_started(self) -> bool:
        return self.status != ProgressRecord.Status.NOT_STARTED


def _build_progress_snapshot(
    *,
    user_id: int,
    lesson: Lesson,
    record: ProgressRecord | None,
) -> LessonProgressSnapshot:
    return LessonProgressSnapshot(
        progress_id=record.id if record is not None else None,
        user_id=user_id,
        course_id=lesson.module.course_id,
        module_id=lesson.module_id,
        module_position=lesson.module.position,
        lesson_id=lesson.id,
        lesson_position=lesson.position,
        status=str(record.status) if record is not None else str(ProgressRecord.Status.NOT_STARTED),
        first_opened_at=record.first_opened_at if record is not None else None,
        last_opened_at=record.last_opened_at if record is not None else None,
        completed_at=record.completed_at if record is not None else None,
        source=record.source if record is not None else "",
        metadata=dict(record.metadata or {}) if record is not None else {},
        has_record=record is not None,
    )


def list_progress_for_user(
    *,
    user_id: int,
    course_id: int | None = None,
) -> QuerySet[ProgressRecord]:
    queryset = ProgressRecord.objects.filter(user_id=user_id).select_related(
        "course",
        "module",
        "lesson",
    )
    if course_id is not None:
        queryset = queryset.filter(course_id=course_id)
    return queryset.order_by(*ProgressRecord._meta.ordering)


def list_progress_for_course(
    *,
    user_id: int,
    course_id: int,
) -> list[LessonProgressSnapshot]:
    lessons = list(
        Lesson.objects.select_related("module", "module__course")
        .filter(module__course_id=course_id)
        .order_by("module__position", "position", "id")
    )
    records_by_lesson_id = {
        record.lesson_id: record
        for record in list_progress_for_user(user_id=user_id, course_id=course_id)
    }
    return [
        _build_progress_snapshot(
            user_id=user_id,
            lesson=lesson,
            record=records_by_lesson_id.get(lesson.id),
        )
        for lesson in lessons
    ]


def get_progress_for_lesson(
    user_id: int,
    lesson_id: int,
) -> LessonProgressSnapshot:
    lesson = Lesson.objects.select_related("module", "module__course").get(id=lesson_id)
    record = (
        ProgressRecord.objects.filter(user_id=user_id, lesson_id=lesson_id)
        .only(
            "id",
            "status",
            "first_opened_at",
            "last_opened_at",
            "completed_at",
            "source",
            "metadata",
        )
        .first()
    )
    return _build_progress_snapshot(user_id=user_id, lesson=lesson, record=record)


def complete_lesson(
    user_id: int,
    lesson_id: int,
    source: str = "lesson_player",
    metadata: Mapping[str, Any] | None = None,
) -> ProgressRecord:
    return update_progress(
        user_id=user_id,
        lesson_id=lesson_id,
        status=ProgressRecord.Status.COMPLETED,
        source=source,
        metadata=metadata,
    )


@transaction.atomic
def update_progress(
    *,
    user_id: int,
    lesson_id: int,
    status: str,
    source: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ProgressRecord:
    lesson = Lesson.objects.select_related("module", "module__course").get(id=lesson_id)
    now = timezone.now()
    record, _created = ProgressRecord.objects.select_for_update().get_or_create(
        user_id=user_id,
        lesson=lesson,
        defaults={
            "course": lesson.module.course,
            "module": lesson.module,
            "status": ProgressRecord.Status.NOT_STARTED,
        },
    )
    changed = False

    if status in {ProgressRecord.Status.OPENED, ProgressRecord.Status.IN_PROGRESS}:
        if record.status != ProgressRecord.Status.COMPLETED:
            if record.status != status:
                record.status = status
                changed = True
            previous_open_window = (record.first_opened_at, record.last_opened_at)
            record.mark_opened(when=now)
            if (record.first_opened_at, record.last_opened_at) != previous_open_window:
                changed = True
    elif status == ProgressRecord.Status.COMPLETED:
        if record.status != ProgressRecord.Status.COMPLETED:
            previous_completion_state = (
                record.status,
                record.first_opened_at,
                record.last_opened_at,
                record.completed_at,
            )
            record.mark_completed(when=now)
            if (
                record.status,
                record.first_opened_at,
                record.last_opened_at,
                record.completed_at,
            ) != previous_completion_state:
                changed = True
    elif (
        status == ProgressRecord.Status.NOT_STARTED
        and record.status != ProgressRecord.Status.COMPLETED
    ):
        if record.status != ProgressRecord.Status.NOT_STARTED:
            record.status = ProgressRecord.Status.NOT_STARTED
            changed = True
    else:
        raise ValueError(f"Неподдерживаемый статус прогресса: {status}")

    if record.source != source:
        record.source = source
        changed = True
    if metadata:
        merged_metadata = {**record.metadata, **dict(metadata)}
        if merged_metadata != record.metadata:
            record.metadata = merged_metadata
            changed = True
    if changed:
        record.save()
    return record
