from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.access_control.models import Tariff
from apps.commerce.models import Order
from apps.commerce.services import create_checkout_placeholder
from apps.curriculum.models import Course

pytestmark = pytest.mark.django_db


def create_checkout_context(*, username: str = "buyer") -> tuple[Any, Course, Tariff]:
    user = get_user_model().objects.create_user(username=username, password="pass")
    course = Course.objects.create(slug=f"{username}-course", title="Gatsa Sales")
    tariff = Tariff.objects.create(
        code=Tariff.Code.BASE,
        course=course,
        title="Базовый",
        price_amount=Decimal("50000.00"),
    )
    return user, course, tariff


def create_order(*, user_id: int, tariff: Tariff, course_slug: str) -> Order:
    checkout = create_checkout_placeholder(
        user_id=user_id,
        tariff_id=tariff.id,
        return_path=reverse(
            "curriculum:course_preview",
            kwargs={"course_slug": course_slug},
        ),
    )
    return Order.objects.get(id=checkout.order_id)


def assert_login_redirect(response, *, next_path: str) -> None:
    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.path == reverse("accounts:login")
    assert parse_qs(location.query) == {"next": [next_path]}


def test_checkout_placeholder_api_creates_order_for_authenticated_user() -> None:
    client = Client()
    user, _course, tariff = create_checkout_context()
    client.force_login(user)

    response = client.post(reverse("commerce:checkout_placeholder", args=[tariff.code]))

    assert response.status_code == 201
    payload = response.json()
    order = Order.objects.get(number=payload["order_number"])
    assert payload["provider_code"] == "robokassa"
    assert payload["tariff_code"] == tariff.code
    assert payload["return_path"] == "/learn/"
    assert order.user_id == user.id
    assert order.status == Order.Status.CREATED


def test_checkout_start_redirects_to_order_page_with_course_preview_return_path() -> None:
    client = Client()
    user, course, tariff = create_checkout_context()
    client.force_login(user)

    response = client.post(reverse("commerce:checkout_start", args=[tariff.code]))

    order = Order.objects.get(user=user)
    assert response.status_code == 302
    assert response.headers["Location"] == reverse(
        "commerce:checkout_order",
        kwargs={"public_id": order.public_id},
    )
    assert order.return_path == reverse(
        "curriculum:course_preview",
        kwargs={"course_slug": course.slug},
    )


def test_checkout_order_page_is_visible_to_owner() -> None:
    client = Client()
    user, course, tariff = create_checkout_context()
    order = create_order(user_id=user.id, tariff=tariff, course_slug=course.slug)
    client.force_login(user)

    response = client.get(reverse("commerce:checkout_order", kwargs={"public_id": order.public_id}))

    template_names = {template.name for template in response.templates if template.name}
    body = response.content.decode("utf-8")
    assert response.status_code == 200
    assert "commerce/checkout_placeholder.html" in template_names
    assert "Robokassa" in body
    assert "Реальная оплата пока не подключена." in body
    assert order.number in body
    assert tariff.title in body
    assert "50 000 ₽" in body
    assert "Создан" in body


def test_checkout_order_page_returns_404_for_foreign_user() -> None:
    client = Client()
    owner, course, tariff = create_checkout_context(username="owner")
    stranger = get_user_model().objects.create_user(username="stranger", password="pass")
    order = create_order(user_id=owner.id, tariff=tariff, course_slug=course.slug)
    client.force_login(stranger)

    response = client.get(reverse("commerce:checkout_order", kwargs={"public_id": order.public_id}))

    assert response.status_code == 404


@pytest.mark.parametrize("route_kind", ["start", "order"])
def test_anonymous_checkout_routes_redirect_to_custom_login(route_kind: str) -> None:
    client = Client()
    user, course, tariff = create_checkout_context()
    order = create_order(user_id=user.id, tariff=tariff, course_slug=course.slug)

    if route_kind == "start":
        target_path = reverse("commerce:checkout_start", args=[tariff.code])
        response = client.post(target_path)
    else:
        target_path = reverse("commerce:checkout_order", kwargs={"public_id": order.public_id})
        response = client.get(target_path)

    assert_login_redirect(response, next_path=target_path)
