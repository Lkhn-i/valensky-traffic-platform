from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Max, Q, QuerySet
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.curriculum.models import Lesson

from .models import HomeworkAssignment, HomeworkReview, HomeworkSubmission

MAX_HOMEWORK_ATTACHMENT_BYTES = 25 * 1024 * 1024


class HomeworkAssignmentService(Protocol):
    def list_assignments(
        self,
        *,
        publication_status: str | None = None,
    ) -> QuerySet[HomeworkAssignment]:
        ...

    def get_assignment(self, *, slug: str) -> HomeworkAssignment:
        ...


class HomeworkSubmissionService(Protocol):
    def list_submissions(
        self,
        *,
        assignment: HomeworkAssignment,
        author_identifier: str | None = None,
    ) -> QuerySet[HomeworkSubmission]:
        ...

    def get_next_attempt_number(
        self,
        *,
        assignment: HomeworkAssignment,
        author_identifier: str,
    ) -> int:
        ...


class HomeworkReviewService(Protocol):
    def list_reviews(self, *, submission: HomeworkSubmission) -> QuerySet[HomeworkReview]:
        ...


class ORMHomeworkAssignmentService:
    def list_assignments(
        self,
        *,
        publication_status: str | None = None,
    ) -> QuerySet[HomeworkAssignment]:
        queryset = HomeworkAssignment.objects.all()
        if publication_status:
            queryset = queryset.filter(publication_status=publication_status)
        return queryset.order_by(*HomeworkAssignment._meta.ordering)

    def get_assignment(self, *, slug: str) -> HomeworkAssignment:
        return self.list_assignments().get(slug=slug)


class StubHomeworkAssignmentService:
    def list_assignments(
        self,
        *,
        publication_status: str | None = None,
    ) -> QuerySet[HomeworkAssignment]:
        return HomeworkAssignment.objects.none()

    def get_assignment(self, *, slug: str) -> HomeworkAssignment:
        raise HomeworkAssignment.DoesNotExist(
            f"Домашнее задание со slug={slug!r} недоступно в заглушке"
        )


class ORMHomeworkSubmissionService:
    def list_submissions(
        self,
        *,
        assignment: HomeworkAssignment,
        author_identifier: str | None = None,
    ) -> QuerySet[HomeworkSubmission]:
        queryset = HomeworkSubmission.objects.filter(assignment=assignment)
        if author_identifier:
            queryset = queryset.filter(author_identifier=author_identifier)
        return queryset.order_by(*HomeworkSubmission._meta.ordering)

    def get_next_attempt_number(
        self,
        *,
        assignment: HomeworkAssignment,
        author_identifier: str,
    ) -> int:
        aggregate = self.list_submissions(
            assignment=assignment,
            author_identifier=author_identifier,
        ).aggregate(max_attempt_number=Max("attempt_number"))
        return int(aggregate["max_attempt_number"] or 0) + 1


class StubHomeworkSubmissionService:
    def list_submissions(
        self,
        *,
        assignment: HomeworkAssignment,
        author_identifier: str | None = None,
    ) -> QuerySet[HomeworkSubmission]:
        return HomeworkSubmission.objects.none()

    def get_next_attempt_number(
        self,
        *,
        assignment: HomeworkAssignment,
        author_identifier: str,
    ) -> int:
        return 1


class ORMHomeworkReviewService:
    def list_reviews(self, *, submission: HomeworkSubmission) -> QuerySet[HomeworkReview]:
        return HomeworkReview.objects.filter(submission=submission).order_by(
            *HomeworkReview._meta.ordering
        )


class StubHomeworkReviewService:
    def list_reviews(self, *, submission: HomeworkSubmission) -> QuerySet[HomeworkReview]:
        return HomeworkReview.objects.none()


@dataclass(frozen=True, slots=True)
class HomeworkAttachmentView:
    filename: str
    url: str
    size_label: str


@dataclass(frozen=True, slots=True)
class LessonHomeworkAssignmentView:
    public_id: str
    slug: str
    title: str
    summary: str
    prompt: str
    max_attempts: int
    status_code: str
    status_label: str
    can_submit: bool
    answer_text: str
    feedback_text: str
    attempts_used: int
    attempts_left: int
    submitted_at: datetime | None
    attachments: tuple[HomeworkAttachmentView, ...]


@dataclass(frozen=True, slots=True)
class HomeworkGateDecision:
    allowed: bool
    reason: str
    reason_label: str
    lesson_id: int | None = None
    lesson_title: str = ""
    assignment_id: int | None = None
    assignment_slug: str = ""
    assignment_title: str = ""


def homework_author_identifier(user_id: int) -> str:
    return f"user:{user_id}"


def list_assignments_for_lesson(
    *,
    lesson_id: int,
    publication_status: str = "published",
) -> QuerySet[HomeworkAssignment]:
    return HomeworkAssignment.objects.filter(
        target_reference_type="lesson",
        target_reference_key=str(lesson_id),
        publication_status=publication_status,
    ).order_by(*HomeworkAssignment._meta.ordering)


def _extract_text_answer(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    answer = payload.get("text_answer")
    return answer.strip() if isinstance(answer, str) else ""


def _attachment_size_label(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} МБ"
    if size >= 1024:
        return f"{size / 1024:.1f} КБ"
    return f"{size} Б"


def _extract_attachments(payload: object) -> tuple[HomeworkAttachmentView, ...]:
    if not isinstance(payload, dict):
        return ()
    raw_attachments = payload.get("attachments")
    if not isinstance(raw_attachments, list):
        return ()

    attachments: list[HomeworkAttachmentView] = []
    for raw_attachment in raw_attachments:
        if not isinstance(raw_attachment, dict):
            continue
        filename = raw_attachment.get("filename")
        storage_path = raw_attachment.get("storage_path")
        size = raw_attachment.get("size", 0)
        if not isinstance(filename, str) or not isinstance(storage_path, str):
            continue
        attachments.append(
            HomeworkAttachmentView(
                filename=filename,
                url=default_storage.url(storage_path),
                size_label=_attachment_size_label(size if isinstance(size, int) else 0),
            )
        )
    return tuple(attachments)


def _safe_homework_author_path(author_identifier: str) -> str:
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in author_identifier
    )


def _store_homework_attachments(
    *,
    assignment: HomeworkAssignment,
    author_identifier: str,
    uploaded_files: Sequence[UploadedFile],
) -> list[dict[str, object]]:
    stored_attachments: list[dict[str, object]] = []
    safe_author = _safe_homework_author_path(author_identifier)
    uploaded_at = timezone.now().isoformat()

    for uploaded_file in uploaded_files:
        if uploaded_file.size == 0:
            continue
        if uploaded_file.size > MAX_HOMEWORK_ATTACHMENT_BYTES:
            raise ValueError("Файл домашнего задания больше 25 МБ.")

        safe_name = get_valid_filename(uploaded_file.name) or "attachment"
        storage_path = default_storage.save(
            f"homework/{assignment.public_id}/{safe_author}/{uuid4().hex}-{safe_name}",
            uploaded_file,
        )
        stored_attachments.append(
            {
                "filename": uploaded_file.name,
                "storage_path": storage_path,
                "size": uploaded_file.size,
                "content_type": getattr(uploaded_file, "content_type", "") or "",
                "uploaded_at": uploaded_at,
            }
        )

    return stored_attachments


def _homework_submission_payload(
    *,
    assignment: HomeworkAssignment,
    author_identifier: str,
    answer_text: str,
    uploaded_files: Sequence[UploadedFile],
) -> dict[str, object]:
    attachment_payload = _store_homework_attachments(
        assignment=assignment,
        author_identifier=author_identifier,
        uploaded_files=uploaded_files,
    )
    payload: dict[str, object] = {"text_answer": answer_text}
    if attachment_payload:
        payload["attachments"] = attachment_payload
    return payload


def _status_for_submission(
    *,
    submission: HomeworkSubmission | None,
) -> tuple[str, str]:
    if submission is None:
        return ("missing", "Не отправлено")
    if submission.submission_state == HomeworkSubmission.SubmissionState.SUBMITTED:
        return ("submitted", "На проверке")
    if submission.submission_state == HomeworkSubmission.SubmissionState.REVIEWED:
        return ("reviewed", "Проверено")
    if submission.submission_state == HomeworkSubmission.SubmissionState.RETURNED:
        return ("returned", "Нужна доработка")
    return ("draft", "Черновик")


def _can_submit_again(
    *,
    assignment: HomeworkAssignment,
    latest_submission: HomeworkSubmission | None,
    attempts_used: int,
) -> bool:
    if latest_submission is None:
        return True
    if latest_submission.submission_state == HomeworkSubmission.SubmissionState.DRAFT:
        return True
    if latest_submission.submission_state == HomeworkSubmission.SubmissionState.RETURNED:
        return attempts_used < assignment.max_attempts
    return False


def list_assignment_views_for_lesson(
    *,
    lesson_id: int,
    author_identifier: str,
) -> tuple[LessonHomeworkAssignmentView, ...]:
    submission_service = ORMHomeworkSubmissionService()
    review_service = ORMHomeworkReviewService()
    assignment_views: list[LessonHomeworkAssignmentView] = []

    for assignment in list_assignments_for_lesson(lesson_id=lesson_id):
        submissions = list(
            submission_service.list_submissions(
                assignment=assignment,
                author_identifier=author_identifier,
            )
        )
        latest_submission = submissions[0] if submissions else None
        latest_review = None
        if latest_submission is not None:
            reviews = list(review_service.list_reviews(submission=latest_submission)[:1])
            latest_review = reviews[0] if reviews else None
        attempts_used = len(submissions)
        attempts_left = max(assignment.max_attempts - attempts_used, 0)
        status_code, status_label = _status_for_submission(submission=latest_submission)

        assignment_views.append(
            LessonHomeworkAssignmentView(
                public_id=str(assignment.public_id),
                slug=assignment.slug,
                title=assignment.title,
                summary=assignment.summary,
                prompt=assignment.prompt,
                max_attempts=assignment.max_attempts,
                status_code=status_code,
                status_label=status_label,
                can_submit=_can_submit_again(
                    assignment=assignment,
                    latest_submission=latest_submission,
                    attempts_used=attempts_used,
                ),
                answer_text=_extract_text_answer(
                    latest_submission.payload if latest_submission is not None else {}
                ),
                feedback_text=latest_review.feedback if latest_review is not None else "",
                attempts_used=attempts_used,
                attempts_left=attempts_left,
                submitted_at=(
                    latest_submission.submitted_at if latest_submission is not None else None
                ),
                attachments=_extract_attachments(
                    latest_submission.payload if latest_submission is not None else {}
                ),
            )
        )

    return tuple(assignment_views)


def _latest_submission_for_assignment(
    *,
    assignment: HomeworkAssignment,
    author_identifier: str,
) -> HomeworkSubmission | None:
    return (
        HomeworkSubmission.objects.filter(
            assignment=assignment,
            author_identifier=author_identifier,
        )
        .order_by(*HomeworkSubmission._meta.ordering)
        .first()
    )


def _has_approved_review(
    *,
    assignment: HomeworkAssignment,
    author_identifier: str,
) -> bool:
    return HomeworkReview.objects.filter(
        submission__assignment=assignment,
        submission__author_identifier=author_identifier,
        decision=HomeworkReview.ReviewDecision.APPROVED,
    ).exists()


def _homework_gate_blocker(
    *,
    lesson: Lesson,
    assignment: HomeworkAssignment,
    author_identifier: str,
) -> HomeworkGateDecision:
    latest_submission = _latest_submission_for_assignment(
        assignment=assignment,
        author_identifier=author_identifier,
    )
    reason = "homework_missing"
    reason_label = "Сначала отправьте домашку."
    if latest_submission is not None:
        if latest_submission.submission_state == HomeworkSubmission.SubmissionState.SUBMITTED:
            reason = "homework_pending_review"
            reason_label = "Домашка отправлена и ждёт проверки."
        elif latest_submission.submission_state == HomeworkSubmission.SubmissionState.RETURNED:
            reason = "homework_changes_requested"
            reason_label = "Менеджер вернул домашку на доработку."
        elif latest_submission.submission_state == HomeworkSubmission.SubmissionState.REVIEWED:
            reason = "homework_not_approved"
            reason_label = "Домашка проверена, но пока не принята."

    return HomeworkGateDecision(
        allowed=False,
        reason=reason,
        reason_label=reason_label,
        lesson_id=lesson.id,
        lesson_title=lesson.title,
        assignment_id=assignment.id,
        assignment_slug=assignment.slug,
        assignment_title=assignment.title,
    )


def check_lesson_homework_gate(
    *,
    lesson_id: int,
    author_identifier: str,
) -> HomeworkGateDecision:
    lesson = Lesson.objects.select_related("module", "module__course").get(id=lesson_id)
    assignments = list(list_assignments_for_lesson(lesson_id=lesson_id))
    for assignment in assignments:
        if not _has_approved_review(
            assignment=assignment,
            author_identifier=author_identifier,
        ):
            return _homework_gate_blocker(
                lesson=lesson,
                assignment=assignment,
                author_identifier=author_identifier,
            )
    return HomeworkGateDecision(allowed=True, reason="homework_ready", reason_label="")


def find_previous_homework_blocker(
    *,
    lesson: Lesson,
    author_identifier: str,
) -> HomeworkGateDecision:
    previous_lessons = Lesson.objects.select_related("module", "module__course").filter(
        Q(module__position__lt=lesson.module.position)
        | Q(module__position=lesson.module.position, position__lt=lesson.position)
        | Q(
            module__position=lesson.module.position,
            position=lesson.position,
            id__lt=lesson.id,
        ),
        module__course_id=lesson.module.course_id,
        publication_status=Lesson.PublicationStatus.PUBLISHED,
    ).order_by("module__position", "position", "id")

    for previous_lesson in previous_lessons:
        decision = check_lesson_homework_gate(
            lesson_id=previous_lesson.id,
            author_identifier=author_identifier,
        )
        if not decision.allowed:
            return decision
    return HomeworkGateDecision(allowed=True, reason="previous_homework_ready", reason_label="")


@transaction.atomic
def submit_text_answer(
    *,
    assignment: HomeworkAssignment,
    author_identifier: str,
    answer_text: str,
    attachments: Sequence[UploadedFile] | None = None,
) -> HomeworkSubmission:
    answer_text = answer_text.strip()
    uploaded_files = tuple(attachments or ())
    if assignment.publication_status != HomeworkAssignment.PublicationStatus.PUBLISHED:
        raise ValueError("Домашнее задание недоступно для отправки.")
    if not answer_text and not uploaded_files:
        raise ValueError("Напишите ответ перед отправкой.")

    submissions = list(
        HomeworkSubmission.objects.select_for_update()
        .filter(assignment=assignment, author_identifier=author_identifier)
        .order_by(*HomeworkSubmission._meta.ordering)
    )
    latest_submission = submissions[0] if submissions else None

    if (
        latest_submission is not None
        and latest_submission.submission_state == HomeworkSubmission.SubmissionState.SUBMITTED
    ):
        raise ValueError("Ответ уже отправлен и ждёт проверки.")

    submitted_at = timezone.now()
    if (
        latest_submission is not None
        and latest_submission.submission_state == HomeworkSubmission.SubmissionState.DRAFT
    ):
        latest_submission.payload = _homework_submission_payload(
            assignment=assignment,
            author_identifier=author_identifier,
            answer_text=answer_text,
            uploaded_files=uploaded_files,
        )
        latest_submission.submission_state = HomeworkSubmission.SubmissionState.SUBMITTED
        latest_submission.submitted_at = submitted_at
        latest_submission.notes = ""
        latest_submission.save(
            update_fields=[
                "payload",
                "submission_state",
                "submitted_at",
                "notes",
                "updated_at",
            ]
        )
        return latest_submission

    if len(submissions) >= assignment.max_attempts:
        raise ValueError("Лимит попыток для этой домашки исчерпан.")

    next_attempt_number = latest_submission.attempt_number + 1 if latest_submission else 1
    return HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier=author_identifier,
        attempt_number=next_attempt_number,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
        payload=_homework_submission_payload(
            assignment=assignment,
            author_identifier=author_identifier,
            answer_text=answer_text,
            uploaded_files=uploaded_files,
        ),
        submitted_at=submitted_at,
    )
