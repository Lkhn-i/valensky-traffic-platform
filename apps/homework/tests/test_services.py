import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.curriculum.models import Course, Lesson, Module
from apps.homework.models import HomeworkAssignment, HomeworkReview, HomeworkSubmission
from apps.homework.services import (
    ORMHomeworkAssignmentService,
    ORMHomeworkReviewService,
    ORMHomeworkSubmissionService,
    StubHomeworkAssignmentService,
    StubHomeworkReviewService,
    StubHomeworkSubmissionService,
    check_lesson_homework_gate,
    find_previous_homework_blocker,
    homework_author_identifier,
    list_assignment_views_for_lesson,
    list_assignments_for_lesson,
    submit_text_answer,
)


@pytest.mark.django_db
def test_homework_services_cover_assignments_submissions_and_reviews() -> None:
    assignment = HomeworkAssignment.objects.create(
        slug="essay-1",
        title="Essay 1",
        publication_status="published",
        max_attempts=3,
    )
    first_submission = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier="student-1",
        attempt_number=1,
        submission_state="submitted",
    )
    HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier="student-1",
        attempt_number=2,
        submission_state="draft",
    )
    review = HomeworkReview.objects.create(
        submission=first_submission,
        reviewer_identifier="mentor-1",
        decision="approved",
        score=95,
    )

    assignment_service = ORMHomeworkAssignmentService()
    submission_service = ORMHomeworkSubmissionService()
    review_service = ORMHomeworkReviewService()

    assert list(
        assignment_service.list_assignments(
            publication_status="published"
        )
    ) == [assignment]
    assert assignment_service.get_assignment(slug=assignment.slug) == assignment
    assert submission_service.get_next_attempt_number(
        assignment=assignment,
        author_identifier="student-1",
    ) == 3
    assert list(
        submission_service.list_submissions(
            assignment=assignment,
            author_identifier="student-1",
        )
    )[0].attempt_number == 2
    assert list(review_service.list_reviews(submission=first_submission)) == [review]


def test_homework_stub_services_are_safe() -> None:
    assignment_service = StubHomeworkAssignmentService()
    submission_service = StubHomeworkSubmissionService()
    review_service = StubHomeworkReviewService()

    assignment = HomeworkAssignment(slug="stub", title="Stub")
    submission = HomeworkSubmission(
        assignment=assignment,
        author_identifier="student-1",
        attempt_number=1,
    )

    assert list(assignment_service.list_assignments()) == []
    assert list(submission_service.list_submissions(assignment=assignment)) == []
    assert submission_service.get_next_attempt_number(
        assignment=assignment,
        author_identifier="student-1",
    ) == 1
    assert list(review_service.list_reviews(submission=submission)) == []


@pytest.mark.django_db
def test_list_assignments_for_lesson_returns_only_published_lesson_targets() -> None:
    published = HomeworkAssignment.objects.create(
        slug="lesson-task",
        title="Lesson Task",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key="42",
    )
    HomeworkAssignment.objects.create(
        slug="draft-task",
        title="Draft Task",
        publication_status=HomeworkAssignment.PublicationStatus.DRAFT,
        target_reference_type="lesson",
        target_reference_key="42",
    )
    HomeworkAssignment.objects.create(
        slug="other-lesson-task",
        title="Other Lesson Task",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key="43",
    )

    assert list(list_assignments_for_lesson(lesson_id=42)) == [published]


@pytest.mark.django_db
def test_list_assignment_views_for_lesson_exposes_status_feedback_and_retry_state() -> None:
    course = Course.objects.create(slug="homework-course", title="Homework Course")
    module = Module.objects.create(course=course, slug="module-1", title="Module 1", position=0)
    lesson = Lesson.objects.create(module=module, slug="lesson-1", title="Lesson 1", position=0)
    HomeworkAssignment.objects.create(
        slug="pending-homework",
        title="Pending Homework",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson.id),
    )
    returned_assignment = HomeworkAssignment.objects.create(
        slug="returned-homework",
        title="Returned Homework",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson.id),
        max_attempts=2,
    )
    returned_submission = HomeworkSubmission.objects.create(
        assignment=returned_assignment,
        author_identifier="student-1",
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.RETURNED,
        payload={"text_answer": "Первый ответ"},
    )
    HomeworkReview.objects.create(
        submission=returned_submission,
        reviewer_identifier="mentor-1",
        decision=HomeworkReview.ReviewDecision.CHANGES_REQUESTED,
        feedback="Добавьте конкретный пример.",
    )

    assignment_views = list_assignment_views_for_lesson(
        lesson_id=lesson.id,
        author_identifier="student-1",
    )
    view_by_slug = {assignment_view.slug: assignment_view for assignment_view in assignment_views}

    assert view_by_slug["pending-homework"].status_code == "missing"
    assert view_by_slug["pending-homework"].status_label == "Не отправлено"
    assert view_by_slug["pending-homework"].can_submit is True
    assert view_by_slug["returned-homework"].status_code == "returned"
    assert view_by_slug["returned-homework"].feedback_text == "Добавьте конкретный пример."
    assert view_by_slug["returned-homework"].answer_text == "Первый ответ"
    assert view_by_slug["returned-homework"].attempts_left == 1
    assert view_by_slug["returned-homework"].can_submit is True


@pytest.mark.django_db
def test_submit_text_answer_creates_submitted_attempt_and_rejects_duplicate_pending() -> None:
    assignment = HomeworkAssignment.objects.create(
        slug="submit-homework",
        title="Submit Homework",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        max_attempts=2,
    )

    submission = submit_text_answer(
        assignment=assignment,
        author_identifier="student-1",
        answer_text="Готовый текст ответа",
    )

    assert submission.attempt_number == 1
    assert submission.submission_state == HomeworkSubmission.SubmissionState.SUBMITTED
    assert submission.payload == {"text_answer": "Готовый текст ответа"}

    with pytest.raises(ValueError, match="ждёт проверки"):
        submit_text_answer(
            assignment=assignment,
            author_identifier="student-1",
            answer_text="Повторная отправка",
        )

    assert HomeworkSubmission.objects.filter(assignment=assignment).count() == 1


@pytest.mark.django_db
def test_submit_text_answer_accepts_file_attachment(settings, tmp_path) -> None:
    settings.MEDIA_ROOT = tmp_path
    course = Course.objects.create(slug="attachment-course", title="Attachment Course")
    module = Module.objects.create(course=course, slug="module-1", title="Module 1", position=1)
    lesson = Lesson.objects.create(module=module, slug="lesson-1", title="Lesson 1", position=1)
    assignment = HomeworkAssignment.objects.create(
        slug="attachment-homework",
        title="Attachment Homework",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson.id),
    )

    submission = submit_text_answer(
        assignment=assignment,
        author_identifier="student-1",
        answer_text="",
        attachments=(
            SimpleUploadedFile("plan.txt", b"first step", content_type="text/plain"),
        ),
    )
    assignment_view = list_assignment_views_for_lesson(
        lesson_id=lesson.id,
        author_identifier="student-1",
    )[0]

    assert submission.payload["text_answer"] == ""
    assert submission.payload["attachments"][0]["filename"] == "plan.txt"
    assert assignment_view.attachments[0].filename == "plan.txt"


@pytest.mark.django_db
def test_submit_text_answer_creates_new_attempt_after_returned_submission() -> None:
    assignment = HomeworkAssignment.objects.create(
        slug="resubmit-homework",
        title="Resubmit Homework",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        max_attempts=2,
    )
    previous_submission = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier="student-1",
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.RETURNED,
        payload={"text_answer": "Нужна доработка"},
    )
    HomeworkReview.objects.create(
        submission=previous_submission,
        reviewer_identifier="mentor-1",
        decision=HomeworkReview.ReviewDecision.CHANGES_REQUESTED,
    )

    new_submission = submit_text_answer(
        assignment=assignment,
        author_identifier="student-1",
        answer_text="Исправленный ответ",
    )

    previous_submission.refresh_from_db()
    assert previous_submission.submission_state == HomeworkSubmission.SubmissionState.RETURNED
    assert new_submission.attempt_number == 2
    assert new_submission.submission_state == HomeworkSubmission.SubmissionState.SUBMITTED
    assert new_submission.payload["text_answer"] == "Исправленный ответ"


@pytest.mark.django_db
def test_homework_gate_blocks_until_assignment_has_approved_review() -> None:
    course = Course.objects.create(slug="gate-course", title="Gate Course")
    module = Module.objects.create(course=course, slug="module-1", title="Module 1", position=0)
    lesson = Lesson.objects.create(module=module, slug="lesson-1", title="Lesson 1", position=0)
    assignment = HomeworkAssignment.objects.create(
        slug="gate-homework",
        title="Gate Homework",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson.id),
    )
    author_identifier = homework_author_identifier(42)

    missing_decision = check_lesson_homework_gate(
        lesson_id=lesson.id,
        author_identifier=author_identifier,
    )
    submission = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier=author_identifier,
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
    )
    pending_decision = check_lesson_homework_gate(
        lesson_id=lesson.id,
        author_identifier=author_identifier,
    )
    HomeworkReview.objects.create(
        submission=submission,
        reviewer_identifier="mentor-1",
        decision=HomeworkReview.ReviewDecision.APPROVED,
    )
    approved_decision = check_lesson_homework_gate(
        lesson_id=lesson.id,
        author_identifier=author_identifier,
    )

    assert missing_decision.allowed is False
    assert missing_decision.reason == "homework_missing"
    assert pending_decision.allowed is False
    assert pending_decision.reason == "homework_pending_review"
    assert approved_decision.allowed is True


@pytest.mark.django_db
def test_previous_homework_blocker_finds_earlier_lesson_stop_assignment() -> None:
    course = Course.objects.create(slug="previous-gate-course", title="Previous Gate Course")
    module = Module.objects.create(course=course, slug="module-1", title="Module 1", position=0)
    previous_lesson = Lesson.objects.create(
        module=module,
        slug="lesson-1",
        title="Lesson 1",
        publication_status=Lesson.PublicationStatus.PUBLISHED,
        position=0,
    )
    next_lesson = Lesson.objects.create(
        module=module,
        slug="lesson-2",
        title="Lesson 2",
        publication_status=Lesson.PublicationStatus.PUBLISHED,
        position=1,
    )
    assignment = HomeworkAssignment.objects.create(
        slug="previous-homework",
        title="Previous Homework",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(previous_lesson.id),
    )

    blocked = find_previous_homework_blocker(
        lesson=next_lesson,
        author_identifier=homework_author_identifier(7),
    )
    submission = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier=homework_author_identifier(7),
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
    )
    HomeworkReview.objects.create(
        submission=submission,
        reviewer_identifier="mentor-1",
        decision=HomeworkReview.ReviewDecision.APPROVED,
    )
    allowed = find_previous_homework_blocker(
        lesson=next_lesson,
        author_identifier=homework_author_identifier(7),
    )

    assert blocked.allowed is False
    assert blocked.lesson_id == previous_lesson.id
    assert blocked.assignment_slug == "previous-homework"
    assert allowed.allowed is True
