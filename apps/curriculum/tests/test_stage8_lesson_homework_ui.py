import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.access_control.models import Tariff
from apps.access_control.services import grant_paid_access
from apps.accounts.services import assign_role, ensure_required_roles
from apps.curriculum.models import Lesson, Module
from apps.curriculum.services import ensure_stage3_preview_course
from apps.homework.models import HomeworkAssignment, HomeworkReview, HomeworkSubmission
from apps.homework.services import homework_author_identifier
from apps.learning_state.services import complete_lesson


def _lesson0() -> Lesson:
    return Lesson.objects.select_related("module", "module__course").get(
        module__position=0,
        position=0,
    )


def _create_workshop_student_on_second_lesson(client: Client, *, username: str) -> tuple[int, Lesson]:
    ensure_required_roles()
    course = ensure_stage3_preview_course()
    user = get_user_model().objects.create_user(username=username)
    assign_role(user.id, "student")
    client.force_login(user)
    tariff = Tariff.objects.get(code=Tariff.Code.WORKSHOP, course=course)
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)

    workshop = Module.objects.prefetch_related("lessons").get(course=course, slug="workshop")
    lessons = tuple(workshop.lessons.order_by("position", "id"))
    complete_lesson(user.id, _lesson0().id, source="test")
    complete_lesson(user.id, lessons[0].id, source="test")
    return user.id, lessons[1]


@pytest.mark.django_db
def test_stage8_lesson_homework_screen_renders_learning_contract(client: Client) -> None:
    _user_id, lesson = _create_workshop_student_on_second_lesson(
        client,
        username="stage8-homework-pending",
    )
    HomeworkAssignment.objects.create(
        slug="stage8-homework-submit",
        title="Гипотезы, которые дают продажи",
        summary="Подготовьте 5 гипотез для вашего проекта и выберите одну для теста.",
        prompt="Приложите ссылку или коротко опишите выбранную гипотезу.",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson.id),
        max_attempts=2,
    )

    response = client.get(reverse("curriculum:lesson_detail", args=[lesson.id]))

    body = response.content.decode()
    expected_texts = (
        lesson.summary,
        "В процессе",
        "Конспект",
        "Материалы",
        "Домашка",
        "Комментарии",
        "Домашнее задание",
        "Статус домашки",
        "Предыдущий",
        "Следующий",
        "Отправить на проверку",
        "Отметить урок как завершенный",
    )
    missing_texts = [expected_text for expected_text in expected_texts if expected_text not in body]

    assert response.status_code == 200
    assert not missing_texts, f"Missing Stage 8 lesson UI texts: {missing_texts}"
    assert "stage8-player-grid" in body
    assert "stage8-module-row is-current" in body


@pytest.mark.django_db
def test_stage8_lesson_homework_screen_shows_manager_feedback_for_returned_homework(
    client: Client,
) -> None:
    user_id, lesson = _create_workshop_student_on_second_lesson(
        client,
        username="stage8-homework-returned",
    )
    assignment = HomeworkAssignment.objects.create(
        slug="stage8-homework-returned",
        title="Гипотезы, которые дают продажи",
        summary="Подготовьте 5 гипотез для вашего проекта и выберите одну для теста.",
        prompt="Приложите ссылку или коротко опишите выбранную гипотезу.",
        publication_status=HomeworkAssignment.PublicationStatus.PUBLISHED,
        target_reference_type="lesson",
        target_reference_key=str(lesson.id),
        max_attempts=2,
    )
    submission = HomeworkSubmission.objects.create(
        assignment=assignment,
        author_identifier=homework_author_identifier(user_id),
        attempt_number=1,
        submission_state=HomeworkSubmission.SubmissionState.RETURNED,
        payload={"text_answer": "Проверю общий оффер без конкретной аудитории."},
    )
    HomeworkReview.objects.create(
        submission=submission,
        reviewer_identifier="manager",
        decision=HomeworkReview.ReviewDecision.CHANGES_REQUESTED,
        feedback="Хорошие гипотезы, но мало конкретики по офферам. Нужно добавить цифры.",
    )

    response = client.get(reverse("curriculum:lesson_detail", args=[lesson.id]))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Комментарий менеджера" in body
    assert "Нужна доработка" in body
    assert "Доработать и отправить снова" in body
    assert "Хорошие гипотезы, но мало конкретики" in body
