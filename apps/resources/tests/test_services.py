import pytest

from apps.access_control.services import AccessDecision
from apps.curriculum.models import Course, Lesson, LessonBlock, Module
from apps.resources.models import Resource
from apps.resources.services import (
    ORMProtectedLessonResourceService,
    ORMResourceCatalogService,
    ProtectedLessonResourceAccessDenied,
    ProtectedLessonResourceNotFound,
    StubResourceCatalogService,
)


def _build_lesson(*, slug: str = "lesson-resource") -> Lesson:
    course = Course.objects.create(
        slug=f"{slug}-course",
        title=f"{slug} course",
        publication_status=Course.PublicationStatus.PUBLISHED,
    )
    module = Module.objects.create(
        course=course,
        slug=f"{slug}-module",
        title=f"{slug} module",
        publication_status=Module.PublicationStatus.PUBLISHED,
        position=0,
    )
    return Lesson.objects.create(
        module=module,
        slug=slug,
        title=slug,
        publication_status=Lesson.PublicationStatus.PUBLISHED,
        position=0,
    )


@pytest.mark.django_db
def test_resource_catalog_filters_by_state_and_type() -> None:
    Resource.objects.create(
        slug="draft-guide",
        title="Draft Guide",
        resource_type="article",
    )
    published = Resource.objects.create(
        slug="published-checklist",
        title="Published Checklist",
        resource_type="checklist",
        publication_status="published",
    )

    service = ORMResourceCatalogService()

    assert list(
        service.list_resources(
            publication_status="published",
            resource_type="checklist",
        )
    ) == [published]
    assert service.get_resource(slug=published.slug) == published


def test_resource_stub_service_is_empty() -> None:
    service = StubResourceCatalogService()

    assert list(service.list_resources()) == []


@pytest.mark.django_db
def test_protected_resource_service_resolves_matching_download_block(monkeypatch) -> None:
    lesson = _build_lesson()
    resource = Resource.objects.create(
        slug="protected-checklist",
        title="Protected Checklist",
        resource_type=Resource.ResourceType.CHECKLIST,
        publication_status=Resource.PublicationStatus.PUBLISHED,
        download_key="files/protected-checklist.pdf",
    )
    LessonBlock.objects.create(
        lesson=lesson,
        block_type=LessonBlock.BlockType.DOWNLOAD,
        title="Материал",
        payload={"resource_slug": resource.slug},
        position=0,
    )
    captured_calls: list[tuple[int, int]] = []

    def fake_check_access(*, user_id: int, lesson_id: int) -> AccessDecision:
        captured_calls.append((user_id, lesson_id))
        return AccessDecision(allowed=True, reason="paid_access_grant", grant_type="paid")

    monkeypatch.setattr("apps.resources.services.check_access", fake_check_access)

    result = ORMProtectedLessonResourceService().resolve_for_user(
        user_id=42,
        lesson_id=lesson.id,
        resource_slug=resource.slug,
    )

    assert result.lesson == lesson
    assert result.block.payload["resource_slug"] == resource.slug
    assert result.resource == resource
    assert result.access_decision.reason == "paid_access_grant"
    assert captured_calls == [(42, lesson.id)]


@pytest.mark.django_db
def test_protected_resource_service_requires_matching_download_block_before_access_check(
    monkeypatch,
) -> None:
    lesson = _build_lesson(slug="missing-block")
    resource = Resource.objects.create(
        slug="orphan-resource",
        title="Orphan Resource",
        resource_type=Resource.ResourceType.LINK,
        publication_status=Resource.PublicationStatus.PUBLISHED,
        source_url="https://example.com/orphan-resource",
    )
    LessonBlock.objects.create(
        lesson=lesson,
        block_type=LessonBlock.BlockType.ACTION,
        title="Не тот блок",
        payload={"resource_slug": resource.slug},
        position=0,
    )

    def fail_check_access(*, user_id: int, lesson_id: int) -> AccessDecision:
        raise AssertionError("check_access should not run before resource linkage is verified")

    monkeypatch.setattr("apps.resources.services.check_access", fail_check_access)

    with pytest.raises(ProtectedLessonResourceNotFound):
        ORMProtectedLessonResourceService().resolve_for_user(
            user_id=42,
            lesson_id=lesson.id,
            resource_slug=resource.slug,
        )


@pytest.mark.django_db
def test_protected_resource_service_rejects_unpublished_resources_before_access_check(
    monkeypatch,
) -> None:
    lesson = _build_lesson(slug="draft-resource")
    resource = Resource.objects.create(
        slug="draft-only-resource",
        title="Draft Only Resource",
        resource_type=Resource.ResourceType.DOWNLOAD,
        publication_status=Resource.PublicationStatus.DRAFT,
        download_key="files/draft.pdf",
    )
    LessonBlock.objects.create(
        lesson=lesson,
        block_type=LessonBlock.BlockType.DOWNLOAD,
        title="Материал",
        payload={"resource_slug": resource.slug},
        position=0,
    )

    def fail_check_access(*, user_id: int, lesson_id: int) -> AccessDecision:
        raise AssertionError("check_access should not run for unpublished resources")

    monkeypatch.setattr("apps.resources.services.check_access", fail_check_access)

    with pytest.raises(ProtectedLessonResourceNotFound):
        ORMProtectedLessonResourceService().resolve_for_user(
            user_id=7,
            lesson_id=lesson.id,
            resource_slug=resource.slug,
        )


@pytest.mark.django_db
def test_protected_resource_service_raises_permission_error_when_access_denied(
    monkeypatch,
) -> None:
    lesson = _build_lesson(slug="denied-resource")
    resource = Resource.objects.create(
        slug="denied-resource-file",
        title="Denied Resource File",
        resource_type=Resource.ResourceType.DOWNLOAD,
        publication_status=Resource.PublicationStatus.PUBLISHED,
        download_key="files/denied.pdf",
    )
    LessonBlock.objects.create(
        lesson=lesson,
        block_type=LessonBlock.BlockType.DOWNLOAD,
        title="Материал",
        payload={"resource_slug": resource.slug},
        position=0,
    )

    monkeypatch.setattr(
        "apps.resources.services.check_access",
        lambda *, user_id, lesson_id: AccessDecision(
            allowed=False,
            reason="missing_paid_access_grant",
        ),
    )

    with pytest.raises(ProtectedLessonResourceAccessDenied) as exc_info:
        ORMProtectedLessonResourceService().resolve_for_user(
            user_id=101,
            lesson_id=lesson.id,
            resource_slug=resource.slug,
        )

    assert exc_info.value.reason == "missing_paid_access_grant"
