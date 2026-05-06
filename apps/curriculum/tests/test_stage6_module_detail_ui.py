import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.access_control.models import Tariff
from apps.access_control.services import grant_paid_access
from apps.accounts.services import assign_role, ensure_required_roles
from apps.curriculum.models import Lesson, Module
from apps.curriculum.services import ensure_stage3_preview_course


def _lesson0() -> Lesson:
    return Lesson.objects.select_related("module", "module__course").get(
        module__position=0,
        position=0,
    )


def _create_paid_student(client: Client, *, username: str) -> None:
    ensure_required_roles()
    course = ensure_stage3_preview_course()
    user = get_user_model().objects.create_user(username=username)
    assign_role(user.id, "student")
    client.force_login(user)
    tariff = Tariff.objects.get(code=Tariff.Code.BASE, course=course)
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)


@pytest.mark.django_db
def test_module_detail_stage6_ui_shows_module_lesson_interface_contract(
    client: Client,
) -> None:
    _create_paid_student(client, username="stage6-module-detail-ui")
    lesson0 = _lesson0()
    start_module = Module.objects.select_related("course").get(slug="start")

    complete_response = client.post(reverse("curriculum:lesson_complete", args=[lesson0.id]))
    response = client.get(reverse("curriculum:module_detail", args=[start_module.id]))

    body = response.content.decode()

    assert complete_response.status_code == 302
    assert response.status_code == 200
    expected_texts = (
        "Уроки модуля",
        "Уроков в модуле",
        "Выполнено",
        "Домашек",
        "Средний балл",
        "Завершить модуль",
    )
    missing_texts = [expected_text for expected_text in expected_texts if expected_text not in body]
    assert not missing_texts, f"Missing Stage 6 module_detail texts: {missing_texts}"


@pytest.mark.django_db
def test_module_detail_stage6_keeps_locked_reasons_visible_in_lesson_rows(
    client: Client,
) -> None:
    _create_paid_student(client, username="stage6-module-detail-locked")
    lesson0 = _lesson0()
    main_module = Module.objects.select_related("course").get(
        slug="personal-brand-foundation",
    )

    complete_response = client.post(reverse("curriculum:lesson_complete", args=[lesson0.id]))
    response = client.get(reverse("curriculum:module_detail", args=[main_module.id]))

    body = response.content.decode()
    documents_reason = "Перед следующим модулем нужно подтвердить документы по предыдущему модулю."
    previous_lesson_reason = (
        "Сначала завершите предыдущий доступный урок. Перепрыгивать уроки нельзя."
    )

    assert complete_response.status_code == 302
    assert response.status_code == 200
    assert body.count(documents_reason) >= 2
    assert previous_lesson_reason in body
