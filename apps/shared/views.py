from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from apps.access_control.models import Tariff
from apps.curriculum.models import Course

from .services.health import run_healthcheck

LANDING_COURSE_SLUG = "gatsa-sales"

APP_BOUNDARIES = (
    ("accounts", "роли, сессии и профили пользователей"),
    ("diagnostic_handoff", "вход лида после диагностики"),
    ("curriculum", "курсы, модули и уроки"),
    ("resources", "защищённые материалы уроков"),
    ("media_library", "медиафайлы и безопасное воспроизведение"),
    ("commerce", "заказы и будущая оплата"),
    ("access_control", "пробные и платные доступы"),
    ("learning_state", "прогресс и завершение уроков"),
    ("homework", "домашние задания и проверки"),
    ("operator", "поддержка и рабочие процессы команды"),
    ("events", "аналитика и аудит"),
    ("notifications", "очередь сообщений"),
    ("integrations", "адаптеры бота и внешних сервисов"),
    ("shared", "проверка состояния, общий интерфейс и базовые помощники"),
)


def index(request: HttpRequest) -> HttpResponse:
    landing_course = Course.objects.filter(slug=LANDING_COURSE_SLUG).first()
    landing_tariffs = ()
    if landing_course is not None:
        landing_tariffs = tuple(
            Tariff.objects.filter(course=landing_course, is_active=True).order_by(
                *Tariff._meta.ordering
            )
        )

    return render(
        request,
        "shared/index.html",
        {
            "app_boundaries": APP_BOUNDARIES,
            "environment": settings.ENV_NAME,
            "landing_course": landing_course,
            "landing_tariffs": landing_tariffs,
        },
    )


def healthcheck(request: HttpRequest) -> JsonResponse:
    payload, is_healthy = run_healthcheck()
    return JsonResponse(payload, status=200 if is_healthy else 503)
