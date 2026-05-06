from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserTelegramIdentity
from apps.accounts.services import assign_role, ensure_required_roles
from apps.curriculum.models import Course, Lesson, Module
from apps.events.models import AuditLog
from apps.homework.models import HomeworkAssignment, HomeworkReview, HomeworkSubmission
from apps.homework.services import homework_author_identifier
from apps.notifications.models import NotificationJob


def create_user_with_role(*, username: str, role_code: str):
    ensure_required_roles()
    user = get_user_model().objects.create_user(username=username, password="pass")
    assign_role(user.id, role_code)
    return user


def create_course_tree() -> tuple[Course, Module, Lesson]:
    course = Course.objects.create(slug="operator-course", title="Operator Course")
    module = Module.objects.create(
        course=course,
        slug="operator-module",
        title="Operator Module",
        position=0,
    )
    lesson = Lesson.objects.create(
        module=module,
        slug="operator-lesson",
        title="Operator Lesson",
        position=0,
    )
    return course, module, lesson


@pytest.mark.django_db
def test_operator_dashboard_route_is_role_gated() -> None:
    client = Client()
    student = create_user_with_role(username="student-route", role_code="student")
    manager = create_user_with_role(username="manager-route", role_code="manager")

    client.force_login(student)
    denied_response = client.get(reverse("operator:dashboard"))
    client.force_login(manager)
    allowed_response = client.get(reverse("operator:dashboard"))

    assert denied_response.status_code == 403
    assert allowed_response.status_code == 200
    assert "Рабочая панель команды" in allowed_response.content.decode("utf-8")


@pytest.mark.django_db
def test_content_route_publishes_course_and_records_audit() -> None:
    client = Client()
    manager = create_user_with_role(username="manager-content", role_code="admin")
    course, _module, _lesson = create_course_tree()
    client.force_login(manager)

    response = client.post(
        reverse("operator:content"),
        {
            "entity_type": "course",
            "entity_id": str(course.id),
            "status": "published",
            "message": "ready for students",
        },
    )

    course.refresh_from_db()
    assert response.status_code == 302
    assert course.publication_status == Course.PublicationStatus.PUBLISHED
    assert AuditLog.objects.get(action="operator.course.publish").message == (
        "ready for students"
    )


@pytest.mark.django_db
def test_content_route_shows_admin_quick_actions() -> None:
    client = Client()
    manager = create_user_with_role(username="manager-content-links", role_code="manager")
    client.force_login(manager)

    response = client.get(reverse("operator:content"))
    body = response.content.decode("utf-8")

    assert response.status_code == 200
    assert reverse("admin:curriculum_lesson_add") in body
    assert reverse("admin:curriculum_lessonblock_add") in body
    assert reverse("admin:media_library_mediaasset_add") in body
    assert reverse("admin:resources_resource_add") in body
    assert reverse("admin:homework_homeworkassignment_add") in body


@pytest.mark.django_db
def test_learner_detail_resend_access_link_queues_notification_and_audit() -> None:
    client = Client()
    manager = create_user_with_role(username="manager-support", role_code="manager")
    learner = create_user_with_role(username="learner-support", role_code="student")
    learner.email = "learner-support@example.com"
    learner.phone = "+79990000001"
    learner.save(update_fields=["email", "phone"])
    UserTelegramIdentity.objects.create(
        user=learner,
        telegram_id=555111,
        username="learner_support_tg",
    )
    client.force_login(manager)

    detail_response = client.get(reverse("operator:learner_detail", args=[learner.id]))
    resend_response = client.post(
        reverse("operator:resend_access_link", args=[learner.id]),
        {"reason": "student asked in support chat"},
    )

    detail_body = detail_response.content.decode("utf-8")
    assert detail_response.status_code == 200
    assert "Контакты" in detail_body
    assert "learner-support@example.com" in detail_body
    assert "+79990000001" in detail_body
    assert "@learner_support_tg" in detail_body
    assert resend_response.status_code == 302
    notification = NotificationJob.objects.get(template_key="learner.access_link")
    assert notification.user_id == learner.id
    assert notification.payload["path"] == "/learn/"
    assert AuditLog.objects.filter(action="operator.learner.resend_access_link").exists()


@pytest.mark.django_db
def test_homework_review_route_reviews_submission_and_notifies() -> None:
    client = Client()
    manager = create_user_with_role(username="manager-homework", role_code="manager")
    learner = create_user_with_role(username="queue-view-learner", role_code="student")
    learner.email = "queue-view@example.com"
    learner.save(update_fields=["email"])
    assignment = HomeworkAssignment.objects.create(
        slug="operator-homework",
        title="Operator Homework",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
    )
    submission = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier=homework_author_identifier(learner.id),
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
        submitted_at=timezone.now() - timedelta(hours=1),
        payload={"text_answer": "Хочу, чтобы менеджер увидел это превью."},
    )
    client.force_login(manager)

    queue_response = client.get(reverse("operator:homework_queue"))
    review_response = client.post(
        reverse("operator:review_homework", args=[submission.id]),
        {
            "decision": HomeworkReview.ReviewDecision.APPROVED,
            "feedback": "good",
            "score": "90",
        },
    )

    submission.refresh_from_db()
    queue_body = queue_response.content.decode("utf-8")
    assert queue_response.status_code == 200
    assert "Хочу, чтобы менеджер увидел это превью." in queue_body
    assert "queue-view@example.com" in queue_body
    assert reverse("operator:learner_detail", args=[learner.id]) in queue_body
    assert review_response.status_code == 302
    assert submission.submission_state == HomeworkSubmission.SubmissionState.REVIEWED
    assert HomeworkReview.objects.get(submission=submission).feedback == "good"
    assert NotificationJob.objects.filter(template_key="homework.reviewed").exists()
    assert AuditLog.objects.filter(action="operator.homework.review").exists()
