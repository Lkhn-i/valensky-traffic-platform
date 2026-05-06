import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.access_control.models import Tariff
from apps.access_control.services import grant_paid_access
from apps.accounts.services import assign_role, ensure_required_roles
from apps.commerce.models import Order
from apps.curriculum.models import Lesson, Module
from apps.curriculum.services import ensure_stage3_preview_course
from apps.events.models import AnalyticsEvent
from apps.homework.models import HomeworkAssignment, HomeworkReview, HomeworkSubmission
from apps.integrations.models import IntegrationOutboxEvent
from apps.learning_state.models import ProgressRecord
from apps.learning_state.services import complete_lesson
from apps.notifications.models import NotificationJob
from apps.resources.models import Resource


def _lesson0() -> Lesson:
    return Lesson.objects.select_related("module", "module__course").get(
        module__position=0,
        position=0,
    )


@pytest.mark.django_db
def test_learner_dashboard_lists_preview_course_and_continue_action(client: Client) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)

    response = client.get(reverse("curriculum:learner_dashboard"))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Моё обучение" in body
    assert "Курс Гатса: продажи" in body
    assert "Пробный доступ" in body
    assert "Следующий шаг" in body
    assert "Защищённая оплата" in body
    assert "Воркшоп" in body


@pytest.mark.django_db
def test_lesson_player_renders_blocks_video_homework_and_completion_cta(client: Client) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    lesson0 = _lesson0()
    HomeworkAssignment.objects.create(
        slug="lesson0-homework",
        title="Первое действие",
        summary="Опишите один разговор, который нужно улучшить.",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson0.id),
    )

    response = client.get(reverse("curriculum:lesson_detail", args=[lesson0.id]))

    body = response.content.decode()
    resource = Resource.objects.get(slug="lesson-0-first-action-checklist")
    protected_material_url = reverse(
        "resources:protected_lesson_resource",
        kwargs={"lesson_id": lesson0.id, "resource_slug": resource.slug},
    )
    assert response.status_code == 200
    assert "Плеер урока" in body
    assert "Стартовый фокус" in body
    assert "Чек-лист первого действия" in body
    assert protected_material_url in body
    assert resource.download_key not in body
    assert "Первое действие" in body
    assert "Не отправлено" in body
    assert "Стоп-урок" in body
    assert "Сначала отправьте домашку" in body


@pytest.mark.django_db
def test_lesson_homework_submission_updates_status_and_appears_in_operator_queue(
    client: Client,
) -> None:
    ensure_required_roles()
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    lesson0 = _lesson0()
    assignment = HomeworkAssignment.objects.create(
        slug="lesson0-homework-submit",
        title="Первое действие",
        summary="Опишите первый шаг после урока.",
        prompt="Напишите, что именно сделаете в ближайшие 24 часа.",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson0.id),
        max_attempts=2,
    )

    submit_response = client.post(
        reverse("curriculum:lesson_homework_submit", args=[lesson0.id]),
        {
            "assignment_slug": assignment.slug,
            "answer_text": "Сделаю новый скрипт первого касания и отправлю трём лидам.",
        },
    )
    lesson_response = client.get(reverse("curriculum:lesson_detail", args=[lesson0.id]))

    submission = HomeworkSubmission.objects.get(assignment=assignment)
    manager = get_user_model().objects.create_user(username="manager-homework-queue")
    assign_role(manager.id, "manager")
    manager_client = Client()
    manager_client.force_login(manager)
    queue_response = manager_client.get(reverse("operator:homework_queue"))

    lesson_body = lesson_response.content.decode()
    queue_body = queue_response.content.decode()

    assert submit_response.status_code == 302
    assert submit_response.headers["Location"] == reverse(
        "curriculum:lesson_detail",
        args=[lesson0.id],
    )
    assert submission.submission_state == HomeworkSubmission.SubmissionState.SUBMITTED
    assert submission.author_identifier.startswith("user:")
    assert submission.payload["text_answer"] == (
        "Сделаю новый скрипт первого касания и отправлю трём лидам."
    )
    assert AnalyticsEvent.objects.filter(
        name="homework_submitted",
        source_app="homework",
        object_key=str(assignment.id),
    ).exists()
    assert lesson_response.status_code == 200
    assert "На проверке" in lesson_body
    assert "Последний ответ" in lesson_body
    assert queue_response.status_code == 200
    assert "Очередь проверки" in queue_body
    assert assignment.title in queue_body
    assert submission.author_identifier in queue_body


@pytest.mark.django_db
def test_lesson_completion_waits_for_approved_homework(client: Client) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    lesson0 = _lesson0()
    assignment = HomeworkAssignment.objects.create(
        slug="lesson0-homework-gate",
        title="Первое действие",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson0.id),
    )

    missing_response = client.post(reverse("curriculum:lesson_complete", args=[lesson0.id]))
    user_id = int(client.session["_auth_user_id"])
    submission = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier=f"user:{user_id}",
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.SUBMITTED,
    )
    pending_response = client.post(reverse("curriculum:lesson_complete", args=[lesson0.id]))
    HomeworkReview.objects.create(
        submission=submission,
        reviewer_identifier="mentor-1",
        decision=HomeworkReview.ReviewDecision.APPROVED,
    )
    approved_response = client.post(reverse("curriculum:lesson_complete", args=[lesson0.id]))

    assert missing_response.status_code == 400
    assert pending_response.status_code == 400
    assert approved_response.status_code == 302
    assert ProgressRecord.objects.get(lesson=lesson0).status == ProgressRecord.Status.COMPLETED


@pytest.mark.django_db
def test_previous_lesson_homework_stops_next_lesson_even_with_paid_access(
    client: Client,
) -> None:
    ensure_required_roles()
    course = ensure_stage3_preview_course()
    user = get_user_model().objects.create_user(username="homework-gated-student")
    assign_role(user.id, "student")
    client.force_login(user)
    lesson0 = _lesson0()
    lesson1 = Lesson.objects.select_related("module", "module__course").get(slug="lesson-1")
    tariff = Tariff.objects.get(code=Tariff.Code.WORKSHOP, course=course)
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)
    HomeworkAssignment.objects.create(
        slug="lesson0-before-lesson1",
        title="Стоп перед первым платным уроком",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson0.id),
    )

    response = client.get(reverse("curriculum:lesson_detail", args=[lesson1.id]))

    body = response.content.decode()
    assert response.status_code == 403
    assert "Стоп-урок" in body
    assert "Платформа останавливает следующий урок" in body


@pytest.mark.django_db
def test_paid_student_cannot_skip_previous_accessible_lesson(client: Client) -> None:
    ensure_required_roles()
    course = ensure_stage3_preview_course()
    user = get_user_model().objects.create_user(username="sequence-gated-student")
    assign_role(user.id, "student")
    client.force_login(user)
    lesson1 = Lesson.objects.select_related("module", "module__course").get(slug="lesson-1")
    tariff = Tariff.objects.get(code=Tariff.Code.WORKSHOP, course=course)
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)

    response = client.get(reverse("curriculum:lesson_detail", args=[lesson1.id]))

    body = response.content.decode()
    assert response.status_code == 403
    assert "Стоп-урок" in body
    assert "завершение прошлого урока" in body


@pytest.mark.django_db
def test_module_documents_are_required_before_next_paid_module(client: Client) -> None:
    ensure_required_roles()
    course = ensure_stage3_preview_course()
    user = get_user_model().objects.create_user(username="document-gated-student")
    assign_role(user.id, "student")
    client.force_login(user)
    lesson0 = _lesson0()
    start_module = Module.objects.get(course=course, slug="start")
    first_main_lesson = Lesson.objects.select_related("module", "module__course").get(
        slug="lesson-6",
    )
    tariff = Tariff.objects.get(code=Tariff.Code.BASE, course=course)
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)

    complete_response = client.post(reverse("curriculum:lesson_complete", args=[lesson0.id]))
    blocked_response = client.get(reverse("curriculum:lesson_detail", args=[first_main_lesson.id]))
    module_response = client.get(reverse("curriculum:module_detail", args=[start_module.id]))
    missing_checkbox_response = client.post(
        reverse("curriculum:module_complete", args=[start_module.id]),
        {},
    )
    accepted_response = client.post(
        reverse("curriculum:module_complete", args=[start_module.id]),
        {"accept_documents": "on"},
    )
    opened_response = client.get(reverse("curriculum:lesson_detail", args=[first_main_lesson.id]))

    assert complete_response.status_code == 302
    assert complete_response.headers["Location"] == reverse(
        "curriculum:module_detail",
        args=[start_module.id],
    )
    assert blocked_response.status_code == 403
    assert "документы по предыдущему" in blocked_response.content.decode()
    assert module_response.status_code == 200
    assert "Юридическое подтверждение" in module_response.content.decode()
    assert missing_checkbox_response.status_code == 400
    assert "Поставьте галочку" in missing_checkbox_response.content.decode()
    assert accepted_response.status_code == 302
    assert accepted_response.headers["Location"] == reverse(
        "curriculum:lesson_detail",
        args=[first_main_lesson.id],
    )
    assert opened_response.status_code == 200
    assert "Плеер урока" in opened_response.content.decode()


@pytest.mark.django_db
def test_next_module_waits_for_release_schedule_after_documents(client: Client) -> None:
    ensure_required_roles()
    course = ensure_stage3_preview_course()
    user = get_user_model().objects.create_user(username="drip-gated-student")
    assign_role(user.id, "student")
    client.force_login(user)
    tariff = Tariff.objects.get(code=Tariff.Code.BASE, course=course)
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)
    start_module = Module.objects.get(course=course, slug="start")
    module1 = Module.objects.prefetch_related("lessons").get(
        course=course,
        slug="personal-brand-foundation",
    )
    module2_first_lesson = Lesson.objects.select_related("module", "module__course").get(
        slug="lesson-14",
    )

    complete_lesson(user.id, _lesson0().id, source="test")
    client.post(
        reverse("curriculum:module_complete", args=[start_module.id]),
        {"accept_documents": "on"},
    )
    for lesson in module1.lessons.all():
        complete_lesson(user.id, lesson.id, source="test")
    client.post(
        reverse("curriculum:module_complete", args=[module1.id]),
        {"accept_documents": "on"},
    )

    response = client.get(reverse("curriculum:lesson_detail", args=[module2_first_lesson.id]))

    body = response.content.decode()
    assert response.status_code == 403
    assert "расписание курса" in body


@pytest.mark.django_db
def test_lesson_completion_is_idempotent_and_returns_to_course_for_preview_lead(
    client: Client,
) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    lesson0 = _lesson0()

    first_response = client.post(reverse("curriculum:lesson_complete", args=[lesson0.id]))
    second_response = client.post(reverse("curriculum:lesson_complete", args=[lesson0.id]))

    record = ProgressRecord.objects.get(lesson=lesson0)
    assert first_response.status_code == 302
    assert second_response.status_code == 302
    assert first_response.headers["Location"] == reverse(
        "curriculum:course_preview",
        args=[lesson0.module.course.slug],
    )
    assert second_response.headers["Location"] == first_response.headers["Location"]
    assert record.status == ProgressRecord.Status.COMPLETED
    assert ProgressRecord.objects.count() == 1
    assert NotificationJob.objects.filter(template_key="lesson.completed").count() == 1
    assert IntegrationOutboxEvent.objects.filter(event_type="lesson.completed").count() == 1


@pytest.mark.django_db
def test_course_screen_shows_progress_and_marks_modules_outside_paid_tariff_locked(
    client: Client,
) -> None:
    ensure_required_roles()
    course = ensure_stage3_preview_course()
    user = get_user_model().objects.create_user(username="student")
    assign_role(user.id, "student")
    client.force_login(user)
    start_module = Module.objects.get(course=course, slug="start")
    workshop_module = Module.objects.get(course=course, slug="workshop")
    tariff = Tariff.objects.get(code=Tariff.Code.WORKSHOP, course=course)
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)

    response = client.get(reverse("curriculum:course_preview", args=[course.slug]))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Воркшоп" in body
    assert "Завершено: 0 из 6" in body
    assert "Воркшоп 1500" in body
    assert "Фундамент личного бренда" in body
    assert "Platform-safe техничка" in body
    assert "Этот урок не входит в текущий тариф." in body
    assert start_module.title in body
    assert workshop_module.title in body


@pytest.mark.django_db
def test_checkout_start_order_is_visible_on_dashboard_after_preview(
    client: Client,
) -> None:
    client.get(reverse("diagnostic_handoff:simulate_submit"), follow=True)
    course = ensure_stage3_preview_course()
    tariff = Tariff.objects.get(code=Tariff.Code.WORKSHOP, course=course)

    checkout_response = client.post(reverse("commerce:checkout_start", args=[tariff.code]))
    dashboard_response = client.get(reverse("curriculum:learner_dashboard"))

    order = Order.objects.get(tariff=tariff)
    body = dashboard_response.content.decode()
    assert checkout_response.status_code == 302
    assert checkout_response.headers["Location"] == reverse(
        "commerce:checkout_order",
        kwargs={"public_id": order.public_id},
    )
    assert dashboard_response.status_code == 200
    assert "Заказ подготовлен" in body
    assert order.number in body
