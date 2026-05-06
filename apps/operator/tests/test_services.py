from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.access_control.models import Tariff
from apps.access_control.services import grant_paid_access, grant_preview_access
from apps.accounts.models import LeadProfile, UserTelegramIdentity
from apps.accounts.services import assign_role, ensure_required_roles
from apps.commerce.models import Order
from apps.curriculum.models import Course, Lesson, LessonBlock, Module
from apps.diagnostic_handoff.models import DiagnosticHandoff
from apps.events.models import AuditLog
from apps.homework.models import HomeworkAssignment, HomeworkReview, HomeworkSubmission
from apps.homework.services import homework_author_identifier
from apps.learning_state.services import complete_lesson
from apps.operator.services import (
    check_operator_permissions,
    draft_course,
    draft_lesson,
    draft_module,
    get_content_readiness_snapshot,
    get_homework_review_queue,
    get_learner_support_snapshot,
    get_operator_dashboard_metrics,
    publish_course,
    publish_lesson,
    publish_module,
    record_operator_action,
    require_operator_permissions,
)


def create_user_with_role(*, username: str, role_code: str):
    ensure_required_roles()
    user = get_user_model().objects.create_user(username=username)
    assign_role(user.id, role_code)
    return user


def create_course_tree(
    *,
    course_slug: str,
    course_status: str = "draft",
    lesson_status: str = "draft",
) -> tuple[Course, Module, Lesson, Lesson]:
    course = Course.objects.create(
        slug=course_slug,
        title=f"{course_slug} course",
        publication_status=course_status,
    )
    module = Module.objects.create(
        course=course,
        slug=f"{course_slug}-module",
        title=f"{course_slug} module",
        publication_status=course_status,
        position=0,
    )
    lesson0 = Lesson.objects.create(
        module=module,
        slug=f"{course_slug}-lesson-0",
        title=f"{course_slug} lesson 0",
        publication_status=lesson_status,
        position=0,
    )
    lesson1 = Lesson.objects.create(
        module=module,
        slug=f"{course_slug}-lesson-1",
        title=f"{course_slug} lesson 1",
        publication_status=lesson_status,
        position=1,
    )
    for lesson in (lesson0, lesson1):
        LessonBlock.objects.create(
            lesson=lesson,
            block_type=LessonBlock.BlockType.RICH_TEXT,
            title=f"{lesson.slug} block",
            body="Content block for publish readiness.",
            position=0,
        )
    return course, module, lesson0, lesson1


@pytest.mark.django_db
def test_operator_permission_helper_is_role_gated() -> None:
    operator_user = create_user_with_role(username="operator", role_code="manager")
    student_user = create_user_with_role(username="student", role_code="student")

    allowed = check_operator_permissions(user_id=operator_user.id)
    denied = check_operator_permissions(user_id=student_user.id)

    assert allowed.allowed is True
    assert allowed.reason == "operator_role"
    assert denied.allowed is False
    assert denied.reason == "missing_operator_role"
    with pytest.raises(PermissionError):
        require_operator_permissions(user_id=student_user.id, action="publish content")


@pytest.mark.django_db
def test_record_operator_action_persists_stage7_audit_log() -> None:
    operator_user = create_user_with_role(username="auditor", role_code="admin")

    log = record_operator_action(
        action="operator.support.review",
        actor_user_id=operator_user.id,
        target_type="accounts.User",
        target_key="42",
        message="Checked learner access state.",
        payload={"ticket": "SUP-42"},
    )

    stored_log = AuditLog.objects.get(id=log.id)

    assert stored_log.action == "operator.support.review"
    assert stored_log.actor_identifier == str(operator_user.id)
    assert stored_log.target_type == "accounts.User"
    assert stored_log.target_key == "42"
    assert stored_log.payload == {"ticket": "SUP-42"}


@pytest.mark.django_db
def test_content_operations_toggle_publication_states_and_record_audit_logs() -> None:
    operator_user = create_user_with_role(username="manager", role_code="manager")
    course, module, _lesson0, lesson1 = create_course_tree(
        course_slug="stage7",
        course_status="published",
        lesson_status="published",
    )

    draft_course_result = draft_course(
        course_id=course.id,
        actor_user_id=operator_user.id,
        message="Pulled course back to draft.",
    )
    publish_course_result = publish_course(course_id=course.id, actor_user_id=operator_user.id)
    draft_module_result = draft_module(module_id=module.id, actor_user_id=operator_user.id)
    publish_module_result = publish_module(module_id=module.id, actor_user_id=operator_user.id)
    draft_lesson_result = draft_lesson(lesson_id=lesson1.id, actor_user_id=operator_user.id)
    publish_lesson_result = publish_lesson(lesson_id=lesson1.id, actor_user_id=operator_user.id)

    course.refresh_from_db()
    module.refresh_from_db()
    lesson1.refresh_from_db()
    audit_actions = list(
        AuditLog.objects.order_by("id").values_list("action", flat=True)
    )

    assert draft_course_result.updated is True
    assert publish_course_result.updated is True
    assert draft_module_result.updated is True
    assert publish_module_result.updated is True
    assert draft_lesson_result.updated is True
    assert publish_lesson_result.updated is True
    assert course.publication_status == Course.PublicationStatus.PUBLISHED
    assert module.publication_status == Module.PublicationStatus.PUBLISHED
    assert lesson1.publication_status == Lesson.PublicationStatus.PUBLISHED
    assert audit_actions == [
        "operator.course.draft",
        "operator.course.publish",
        "operator.module.draft",
        "operator.module.publish",
        "operator.lesson.draft",
        "operator.lesson.publish",
    ]
    assert AuditLog.objects.get(action="operator.course.draft").message == (
        "Pulled course back to draft."
    )


@pytest.mark.django_db
def test_content_operations_reject_non_operator_actor() -> None:
    student_user = create_user_with_role(username="blocked-student", role_code="student")
    course, _module, _lesson0, _lesson1 = create_course_tree(course_slug="blocked")

    with pytest.raises(PermissionError):
        publish_course(course_id=course.id, actor_user_id=student_user.id)

    course.refresh_from_db()

    assert course.publication_status == Course.PublicationStatus.DRAFT
    assert AuditLog.objects.count() == 0


@pytest.mark.django_db
def test_content_readiness_blocks_publishing_blank_lesson() -> None:
    operator_user = create_user_with_role(username="readiness-manager", role_code="manager")
    _course, _module, _lesson0, lesson1 = create_course_tree(
        course_slug="readiness",
        course_status="published",
        lesson_status="draft",
    )
    LessonBlock.objects.filter(lesson=lesson1).delete()

    readiness = get_content_readiness_snapshot(
        content_type="lesson",
        content_id=lesson1.id,
    )
    with pytest.raises(ValueError, match="В уроке нет ни одного блока"):
        publish_lesson(lesson_id=lesson1.id, actor_user_id=operator_user.id)

    lesson1.refresh_from_db()
    assert readiness.can_publish is False
    assert lesson1.publication_status == Lesson.PublicationStatus.DRAFT
    assert AuditLog.objects.count() == 0


@pytest.mark.django_db
def test_learner_support_snapshot_aggregates_roles_orders_access_grants_and_progress() -> None:
    ensure_required_roles()
    learner = get_user_model().objects.create_user(
        username="learner",
        display_name="Learner Name",
        email="learner@example.com",
        phone="+79990001122",
    )
    assign_role(learner.id, "lead")
    assign_role(learner.id, "student")
    lead_profile = LeadProfile.objects.create(
        user=learner,
        status=LeadProfile.Status.PREVIEW,
    )
    UserTelegramIdentity.objects.create(
        user=learner,
        telegram_id=777000,
        username="learner_tg",
    )
    preview_course, _preview_module, preview_lesson0, _preview_lesson1 = create_course_tree(
        course_slug="preview-course",
        course_status="published",
        lesson_status="published",
    )
    paid_course, _paid_module, _paid_lesson0, paid_lesson1 = create_course_tree(
        course_slug="paid-course",
        course_status="published",
        lesson_status="published",
    )
    grant_preview_access(
        lead_profile_id=lead_profile.id,
        course_id=preview_course.id,
        lesson_id=preview_lesson0.id,
        expires_at=timezone.now() + timedelta(days=2),
    )
    tariff = Tariff.objects.create(code=Tariff.Code.BASE, course=paid_course, title="Базовый")
    paid_grant = grant_paid_access(
        user_id=learner.id,
        course_id=paid_course.id,
        tariff_id=tariff.id,
        source="manual",
        source_reference="operator-stage7-paid",
    )
    Order.objects.create(
        number="STAGE7-ORDER-1",
        user=learner,
        course=paid_course,
        tariff=tariff,
        status=Order.Status.PAID,
        amount=Decimal("9900.00"),
        currency="RUB",
        return_path="/learn/",
        access_grant=paid_grant,
        access_granted_at=timezone.now(),
        paid_at=timezone.now(),
    )
    complete_lesson(learner.id, paid_lesson1.id, source="operator_support")

    snapshot = get_learner_support_snapshot(user_id=learner.id)
    access_by_kind = {grant.grant_kind: grant for grant in snapshot.access_grants}

    assert snapshot.user_id == learner.id
    assert snapshot.username == "learner"
    assert snapshot.display_name == "Learner Name"
    assert snapshot.roles == ("lead", "student")
    assert [order.order_number for order in snapshot.orders] == ["STAGE7-ORDER-1"]
    assert snapshot.orders[0].tariff_code == Tariff.Code.BASE
    assert set(access_by_kind) == {"paid", "preview"}
    assert access_by_kind["paid"].course_slug == "paid-course"
    assert access_by_kind["paid"].tariff_code == Tariff.Code.BASE
    assert access_by_kind["preview"].lesson_slug == preview_lesson0.slug
    assert [progress.lesson_slug for progress in snapshot.progress] == [paid_lesson1.slug]
    assert snapshot.progress[0].status == "completed"
    assert snapshot.contacts.login == "learner"
    assert snapshot.contacts.email == "learner@example.com"
    assert snapshot.contacts.phone == "+79990001122"
    assert snapshot.contacts.telegram_username == "learner_tg"
    assert snapshot.contacts.telegram_link == "https://t.me/learner_tg"
    assert snapshot.contacts.telegram_id == 777000
    assert any(item.allowed for item in snapshot.access_diagnostics)


@pytest.mark.django_db
def test_learner_support_snapshot_explains_missing_paid_access() -> None:
    ensure_required_roles()
    learner = get_user_model().objects.create_user(username="diagnostic-learner")
    assign_role(learner.id, "lead")
    course, _module, _lesson0, lesson1 = create_course_tree(
        course_slug="diagnostic-course",
        course_status="published",
        lesson_status="published",
    )
    tariff = Tariff.objects.create(code=Tariff.Code.BASE, course=course, title="Базовый")
    Order.objects.create(
        number="DIAG-ORDER-PENDING",
        user=learner,
        course=course,
        tariff=tariff,
        status=Order.Status.PENDING,
        amount=Decimal("9900.00"),
        currency="RUB",
        return_path="/pay/",
    )

    snapshot = get_learner_support_snapshot(user_id=learner.id)
    lesson1_diagnosis = next(
        item for item in snapshot.access_diagnostics if item.lesson_id == lesson1.id
    )

    assert lesson1_diagnosis.allowed is False
    assert lesson1_diagnosis.reason == "missing_paid_access_grant"
    assert lesson1_diagnosis.reason_label == "Заказ создан, но платёж ещё не подтверждён."


@pytest.mark.django_db
def test_learner_support_snapshot_uses_metadata_and_diagnostic_fallback_contacts() -> None:
    ensure_required_roles()
    learner = get_user_model().objects.create_user(username="contact-fallback")
    assign_role(learner.id, "lead")
    lead_profile = LeadProfile.objects.create(
        user=learner,
        status=LeadProfile.Status.PREVIEW,
        metadata={"contact": {"email": "fallback@example.com"}},
    )
    DiagnosticHandoff.objects.create(
        source=DiagnosticHandoff.Source.DIAGNOSTIC_SITE,
        external_session_id="fallback-session",
        idempotency_key="fallback-session",
        token_hash="fallback-token",
        user=learner,
        lead_profile=lead_profile,
        raw_payload={"phone": "+79995554433", "telegram_id": 123456},
        expires_at=timezone.now() + timedelta(hours=1),
    )

    snapshot = get_learner_support_snapshot(user_id=learner.id)

    assert snapshot.contacts.login == "contact-fallback"
    assert snapshot.contacts.email == "fallback@example.com"
    assert snapshot.contacts.phone == "+79995554433"
    assert snapshot.contacts.telegram_username == ""
    assert snapshot.contacts.telegram_id == 123456


@pytest.mark.django_db
def test_homework_review_queue_returns_only_submitted_items_without_reviews() -> None:
    ensure_required_roles()
    learner = get_user_model().objects.create_user(
        username="queue-learner",
        display_name="Queue Learner",
        email="queue@example.com",
        phone="+79997776655",
    )
    UserTelegramIdentity.objects.create(
        user=learner,
        telegram_id=888000,
        username="queue_tg",
    )
    assignment = HomeworkAssignment.objects.create(
        slug="queue-assignment",
        title="Queue Assignment",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
    )
    first_pending = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier=homework_author_identifier(learner.id),
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
        submitted_at=timezone.now() - timedelta(hours=2),
        payload={"text_answer": "Готовый текст ответа для менеджера."},
    )
    reviewed_submission = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier="student-2",
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
        submitted_at=timezone.now() - timedelta(hours=1),
    )
    HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier="student-3",
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.DRAFT,
    )
    second_pending = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier="student-4",
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
        submitted_at=timezone.now(),
    )
    HomeworkReview.objects.create(
        submission=reviewed_submission,
        reviewer_identifier="mentor-1",
        decision=HomeworkReview.ReviewDecision.APPROVED,
    )

    queue = get_homework_review_queue()

    assert queue.pending_count == 2
    assert [item.submission_id for item in queue.items] == [
        first_pending.id,
        second_pending.id,
    ]
    assert [item.author_identifier for item in queue.items] == [
        homework_author_identifier(learner.id),
        "student-4",
    ]
    assert queue.items[0].author_user_id == learner.id
    assert queue.items[0].author_display_name == "Queue Learner"
    assert queue.items[0].author_contacts is not None
    assert queue.items[0].author_contacts.email == "queue@example.com"
    assert queue.items[0].author_contacts.telegram_link == "https://t.me/queue_tg"
    assert queue.items[0].answer_preview == "Готовый текст ответа для менеджера."
    assert queue.items[1].author_user_id is None
    assert queue.items[1].author_contacts is None


@pytest.mark.django_db
def test_operator_dashboard_metrics_aggregate_stage7_reporting_counts() -> None:
    create_user_with_role(username="ops", role_code="manager")
    student_user = create_user_with_role(username="student-metrics", role_code="student")
    lead_user = create_user_with_role(username="lead-metrics", role_code="lead")
    lead_profile = LeadProfile.objects.create(user=lead_user, status=LeadProfile.Status.PREVIEW)

    published_course, _published_module, published_lesson0, _published_lesson1 = create_course_tree(
        course_slug="metrics-published",
        course_status="published",
        lesson_status="published",
    )
    draft_course_obj, _draft_module, draft_lesson0, _draft_lesson1 = create_course_tree(
        course_slug="metrics-draft",
        course_status="draft",
        lesson_status="draft",
    )
    base_tariff = Tariff.objects.create(
        code=Tariff.Code.BASE,
        course=published_course,
        title="Базовый",
    )
    mentor_tariff = Tariff.objects.create(
        code=Tariff.Code.MENTOR,
        course=draft_course_obj,
        title="С ментором",
    )
    paid_grant = grant_paid_access(
        user_id=student_user.id,
        course_id=published_course.id,
        tariff_id=base_tariff.id,
        source="payment",
        source_reference="metrics-order-paid",
    )
    grant_preview_access(
        lead_profile_id=lead_profile.id,
        course_id=draft_course_obj.id,
        lesson_id=draft_lesson0.id,
        expires_at=timezone.now() + timedelta(days=1),
    )
    Order.objects.create(
        number="METRICS-ORDER-PAID",
        user=student_user,
        course=published_course,
        tariff=base_tariff,
        status=Order.Status.PAID,
        amount=Decimal("50000.00"),
        currency="RUB",
        return_path="/learn/",
        access_grant=paid_grant,
        access_granted_at=timezone.now(),
        paid_at=timezone.now(),
    )
    Order.objects.create(
        number="METRICS-ORDER-PENDING",
        user=lead_user,
        course=draft_course_obj,
        tariff=mentor_tariff,
        status=Order.Status.PENDING,
        amount=Decimal("9900.00"),
        currency="RUB",
        return_path="/pay/",
    )
    complete_lesson(student_user.id, published_lesson0.id, source="metrics")
    assignment = HomeworkAssignment.objects.create(
        slug="metrics-homework",
        title="Metrics Homework",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
    )
    HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier="student-metrics",
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
        submitted_at=timezone.now(),
    )
    reviewed_submission = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier="lead-metrics",
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
        submitted_at=timezone.now(),
    )
    HomeworkReview.objects.create(
        submission=reviewed_submission,
        reviewer_identifier="mentor-1",
        decision=HomeworkReview.ReviewDecision.APPROVED,
    )

    metrics = get_operator_dashboard_metrics()

    assert metrics.total_users == 3
    assert metrics.operator_users == 1
    assert metrics.learner_users == 2
    assert metrics.paid_orders == 1
    assert metrics.pending_orders == 1
    assert metrics.active_paid_access_grants == 1
    assert metrics.active_preview_access_grants == 1
    assert metrics.published_courses == 1
    assert metrics.draft_courses == 1
    assert metrics.published_lessons == 2
    assert metrics.completed_lessons == 1
    assert metrics.pending_homework_reviews == 1
