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


def _create_workshop_student(client: Client, *, username: str) -> Module:
    ensure_required_roles()
    course = ensure_stage3_preview_course()
    user = get_user_model().objects.create_user(username=username)
    assign_role(user.id, "student")
    client.force_login(user)
    tariff = Tariff.objects.get(code=Tariff.Code.WORKSHOP, course=course)
    grant_paid_access(user_id=user.id, course_id=course.id, tariff_id=tariff.id)
    return Module.objects.select_related("course").get(course=course, slug="workshop")


def _workshop_screen_response(client: Client, *, username: str) -> tuple[object, object, str]:
    workshop_module = _create_workshop_student(client, username=username)
    complete_response = client.post(reverse("curriculum:lesson_complete", args=[_lesson0().id]))
    response = client.get(reverse("curriculum:module_detail", args=[workshop_module.id]))
    return complete_response, response, response.content.decode()


@pytest.mark.django_db
def test_workshop_module_detail_stage7_ui_contract_shows_dedicated_non_zoom_workshop_screen(
    client: Client,
) -> None:
    complete_response, response, body = _workshop_screen_response(
        client,
        username="stage7-workshop-screen",
    )

    expected_texts = (
        "Воркшоп: быстрый запуск трафика",
        "Готов к занятию",
        "Дата и время",
        "LIVE урок",
        "Что сделать до воркшопа",
        "Материалы",
        "Запись",
        "Хочешь систему целиком?",
        "Перейти к занятию",
        "Добавить в календарь",
        "Перейти к полному курсу",
        "Откроется как обычный урок внутри платформы.",
    )
    missing_texts = [expected_text for expected_text in expected_texts if expected_text not in body]

    assert complete_response.status_code == 302
    assert response.status_code == 200
    assert not missing_texts, f"Missing Stage 7 workshop UI texts: {missing_texts}"
    assert body.count("Открыть") >= 2, (
        "Expected separate 'Открыть' actions for workshop materials and recording."
    )
    assert "Перед следующим модулем нужно подтвердить документы" not in body


@pytest.mark.django_db
def test_workshop_module_detail_stage7_ui_contract_keeps_zoom_out_of_workshop_screen(
    client: Client,
) -> None:
    complete_response, response, body = _workshop_screen_response(
        client,
        username="stage7-workshop-clean-screen",
    )

    assert complete_response.status_code == 302
    assert response.status_code == 200
    assert "zoom" not in body.lower()
