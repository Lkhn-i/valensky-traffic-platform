from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.access_control.services import AccessDecision
from apps.curriculum.models import Course, Lesson, LessonBlock, Module
from apps.resources.models import Resource

pytestmark = pytest.mark.django_db


def _build_lesson_with_resource(
    *,
    lesson_slug: str,
    resource_slug: str,
    source_url: str = "",
    download_key: str = "",
) -> tuple[Lesson, Resource]:
    course = Course.objects.create(
        slug=f"{lesson_slug}-course",
        title=f"{lesson_slug} course",
        publication_status=Course.PublicationStatus.PUBLISHED,
    )
    module = Module.objects.create(
        course=course,
        slug=f"{lesson_slug}-module",
        title=f"{lesson_slug} module",
        publication_status=Module.PublicationStatus.PUBLISHED,
        position=0,
    )
    lesson = Lesson.objects.create(
        module=module,
        slug=lesson_slug,
        title=lesson_slug,
        publication_status=Lesson.PublicationStatus.PUBLISHED,
        position=0,
    )
    resource = Resource.objects.create(
        slug=resource_slug,
        title=f"{resource_slug} title",
        resource_type=(
            Resource.ResourceType.LINK if source_url else Resource.ResourceType.DOWNLOAD
        ),
        publication_status=Resource.PublicationStatus.PUBLISHED,
        source_url=source_url,
        download_key=download_key,
    )
    LessonBlock.objects.create(
        lesson=lesson,
        block_type=LessonBlock.BlockType.DOWNLOAD,
        title="Материал",
        payload={"resource_slug": resource.slug},
        position=0,
    )
    return lesson, resource


def _assert_login_redirect(response, *, next_path: str) -> None:
    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.path == reverse("accounts:login")
    assert parse_qs(location.query) == {"next": [next_path]}


def test_protected_lesson_resource_redirects_anonymous_users_to_login(client: Client) -> None:
    target_path = reverse(
        "resources:protected_lesson_resource",
        kwargs={"lesson_id": 999, "resource_slug": "missing"},
    )

    response = client.get(target_path)

    _assert_login_redirect(response, next_path=target_path)


def test_protected_lesson_resource_redirects_to_resource_source_url(
    client: Client,
    monkeypatch,
) -> None:
    lesson, resource = _build_lesson_with_resource(
        lesson_slug="link-lesson",
        resource_slug="sales-script",
        source_url="https://example.com/resources/sales-script",
    )
    user = get_user_model().objects.create_user(username="resource-link-user")
    client.force_login(user)
    monkeypatch.setattr(
        "apps.resources.services.check_access",
        lambda *, user_id, lesson_id: AccessDecision(allowed=True, reason="paid_access_grant"),
    )

    response = client.get(
        reverse(
            "resources:protected_lesson_resource",
            kwargs={"lesson_id": lesson.id, "resource_slug": resource.slug},
        )
    )

    assert response.status_code == 302
    assert response.headers["Location"] == resource.source_url


def test_protected_lesson_resource_returns_placeholder_for_download(
    client: Client,
    monkeypatch,
) -> None:
    lesson, resource = _build_lesson_with_resource(
        lesson_slug="download-lesson",
        resource_slug="call-checklist",
        download_key="files/call-checklist.pdf",
    )
    user = get_user_model().objects.create_user(username="resource-download-user")
    client.force_login(user)
    monkeypatch.setattr(
        "apps.resources.services.check_access",
        lambda *, user_id, lesson_id: AccessDecision(allowed=True, reason="paid_access_grant"),
    )

    response = client.get(
        reverse(
            "resources:protected_lesson_resource",
            kwargs={"lesson_id": lesson.id, "resource_slug": resource.slug},
        )
    )

    body = response.content.decode("utf-8")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert resource.title in body
    assert resource.download_key not in body
    assert "без раскрытия ключа хранения" in body


def test_protected_lesson_resource_returns_403_when_access_denied(
    client: Client,
    monkeypatch,
) -> None:
    lesson, resource = _build_lesson_with_resource(
        lesson_slug="denied-lesson",
        resource_slug="denied-checklist",
        download_key="files/denied-checklist.pdf",
    )
    user = get_user_model().objects.create_user(username="resource-denied-user")
    client.force_login(user)
    monkeypatch.setattr(
        "apps.resources.services.check_access",
        lambda *, user_id, lesson_id: AccessDecision(
            allowed=False,
            reason="missing_paid_access_grant",
        ),
    )

    response = client.get(
        reverse(
            "resources:protected_lesson_resource",
            kwargs={"lesson_id": lesson.id, "resource_slug": resource.slug},
        )
    )

    assert response.status_code == 403
    assert "missing_paid_access_grant" in response.content.decode("utf-8")
