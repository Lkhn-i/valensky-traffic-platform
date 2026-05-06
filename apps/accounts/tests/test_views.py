from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.accounts.services import assign_role, ensure_required_roles

pytestmark = pytest.mark.django_db


def create_user_with_role(*, username: str, role_code: str):
    ensure_required_roles()
    user = get_user_model().objects.create_user(username=username, password="pass")
    assign_role(user.id, role_code)
    return user


def assert_login_redirect(response, *, next_path: str) -> None:
    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.path == reverse("accounts:login")
    assert parse_qs(location.query) == {"next": [next_path]}


@pytest.mark.parametrize(
    ("route_name", "route_kwargs"),
    [
        ("curriculum:learner_dashboard", {}),
        ("operator:dashboard", {}),
    ],
)
def test_protected_routes_redirect_to_custom_login(
    client: Client,
    route_name: str,
    route_kwargs: dict[str, str],
) -> None:
    target_path = reverse(route_name, kwargs=route_kwargs)

    response = client.get(target_path)

    assert_login_redirect(response, next_path=target_path)


def test_login_page_renders_custom_template(client: Client) -> None:
    response = client.get(reverse("accounts:login"))

    template_names = {template.name for template in response.templates if template.name}
    body = response.content.decode("utf-8")
    assert response.status_code == 200
    assert "accounts/login.html" in template_names
    assert "Вход в платформу" in body
    assert 'name="username"' in body
    assert 'name="password"' in body


def test_login_url_is_unified_for_all_roles(client: Client) -> None:
    response = client.get("/login/")
    legacy_response = client.get("/accounts/login/")

    assert response.status_code == 200
    assert reverse("accounts:login") == "/login/"
    assert legacy_response.status_code == 302
    assert legacy_response.headers["Location"] == "/login/"


def test_successful_manager_login_redirects_to_operator_dashboard(client: Client) -> None:
    manager = create_user_with_role(username="manager-login", role_code="manager")

    response = client.post(
        reverse("accounts:login"),
        {"username": manager.username, "password": "pass"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("operator:dashboard")


def test_successful_student_login_redirects_to_learner_dashboard(client: Client) -> None:
    student = create_user_with_role(username="student-login", role_code="student")

    response = client.post(
        reverse("accounts:login"),
        {"username": student.username, "password": "pass"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("curriculum:learner_dashboard")


def test_successful_login_respects_safe_next_redirect(client: Client) -> None:
    manager = create_user_with_role(username="manager-next", role_code="manager")
    next_path = reverse("curriculum:learner_dashboard")

    response = client.post(
        f"{reverse('accounts:login')}?next={next_path}",
        {"username": manager.username, "password": "pass"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == next_path


def test_login_ignores_external_next_redirect(client: Client) -> None:
    manager = create_user_with_role(username="manager-external-next", role_code="manager")

    response = client.post(
        f"{reverse('accounts:login')}?next=https://example.com/phishing",
        {"username": manager.username, "password": "pass"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("operator:dashboard")


def test_invalid_login_keeps_user_on_custom_form(client: Client) -> None:
    create_user_with_role(username="student-invalid-login", role_code="student")

    response = client.post(
        reverse("accounts:login"),
        {"username": "student-invalid-login", "password": "wrong-pass"},
    )

    assert response.status_code == 200
    assert "Вход в платформу" in response.content.decode("utf-8")
    assert response.context is not None
    assert response.context["form"].errors
    assert "_auth_user_id" not in client.session


def test_logout_redirects_to_login(client: Client) -> None:
    student = create_user_with_role(username="student-logout", role_code="student")
    client.force_login(student)

    response = client.get(reverse("accounts:logout"))
    follow_up = client.get(reverse("curriculum:learner_dashboard"))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("accounts:login")
    assert "_auth_user_id" not in client.session
    assert_login_redirect(follow_up, next_path=reverse("curriculum:learner_dashboard"))
