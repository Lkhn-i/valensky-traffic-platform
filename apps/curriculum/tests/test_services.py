from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.access_control.models import Tariff, TariffEntitlement
from apps.curriculum.models import Course, Lesson, LessonBlock, Module
from apps.curriculum.services import (
    STAGE3_PREVIEW_COURSE_SLUG,
    ORMCurriculumCatalogService,
    StubCurriculumCatalogService,
    ensure_stage3_preview_course,
)


@pytest.mark.django_db
def test_curriculum_catalog_returns_ordered_course_tree() -> None:
    course = Course.objects.create(
        slug="sales-course",
        title="Sales Course",
        publication_status="published",
    )
    module = Module.objects.create(
        course=course,
        slug="module-1",
        title="Module 1",
        publication_status="published",
        position=1,
    )
    lesson = Lesson.objects.create(
        module=module,
        slug="lesson-1",
        title="Lesson 1",
        publication_status="published",
        position=1,
    )
    LessonBlock.objects.create(
        lesson=lesson,
        block_type="rich_text",
        title="Intro",
        position=1,
    )

    service = ORMCurriculumCatalogService()
    fetched_course = service.get_course(slug=course.slug)

    assert fetched_course.slug == "sales-course"
    assert list(service.list_courses(publication_status="published")) == [course]
    assert list(service.list_lessons(course_slug=course.slug)) == [lesson]


def test_curriculum_stub_service_is_empty() -> None:
    service = StubCurriculumCatalogService()

    assert list(service.list_courses()) == []
    assert list(service.list_lessons(course_slug="missing")) == []


def _course_outline(course_slug: str) -> list[tuple[str, int, int, str, str]]:
    course = Course.objects.prefetch_related("modules__lessons").get(slug=course_slug)
    return [
        (
            module.slug,
            module.position,
            len(lesson_slugs := [lesson.slug for lesson in module.lessons.all()]),
            lesson_slugs[0],
            lesson_slugs[-1],
        )
        for module in course.modules.all()
    ]


@pytest.mark.django_db
def test_ensure_stage3_preview_course_creates_published_preview_tree() -> None:
    course = ensure_stage3_preview_course()

    assert course.slug == STAGE3_PREVIEW_COURSE_SLUG
    assert course.publication_status == Course.PublicationStatus.PUBLISHED
    assert Course.objects.count() == 1
    assert Module.objects.count() == 9
    assert Lesson.objects.count() == 83
    assert all(
        module.publication_status == Module.PublicationStatus.PUBLISHED
        for module in Module.objects.all()
    )
    assert all(
        lesson.publication_status == Lesson.PublicationStatus.PUBLISHED
        for lesson in Lesson.objects.all()
    )
    assert _course_outline(course.slug) == [
        ("start", 0, 1, "lesson-0", "lesson-0"),
        ("workshop", 1, 5, "lesson-1", "lesson-5"),
        ("personal-brand-foundation", 2, 8, "lesson-6", "lesson-13"),
        ("platform-safe-launch", 3, 11, "lesson-14", "lesson-24"),
        ("content-factory", 4, 14, "lesson-25", "lesson-38"),
        ("monetization-funnels", 5, 15, "lesson-39", "lesson-53"),
        ("paid-organic-growth", 6, 11, "lesson-54", "lesson-64"),
        ("brand-packaging", 7, 9, "lesson-65", "lesson-73"),
        ("sales-and-diagnostics", 8, 9, "lesson-74", "lesson-82"),
    ]
    assert set(Tariff.objects.values_list("code", flat=True)) == {
        Tariff.Code.WORKSHOP,
        Tariff.Code.BASE,
        Tariff.Code.MENTOR,
        Tariff.Code.VIP,
    }
    tariff_snapshot = {
        tariff.code: tariff
        for tariff in Tariff.objects.filter(course=course).order_by("sort_order")
    }
    assert tariff_snapshot[Tariff.Code.WORKSHOP].title == "Воркшоп"
    assert tariff_snapshot[Tariff.Code.WORKSHOP].price_amount == Decimal("1500.00")
    assert tariff_snapshot[Tariff.Code.WORKSHOP].access_duration_days == 14
    assert tariff_snapshot[Tariff.Code.WORKSHOP].metadata["features"]
    assert tariff_snapshot[Tariff.Code.BASE].title == "Базовый"
    assert tariff_snapshot[Tariff.Code.BASE].price_amount == Decimal("50000.00")
    assert tariff_snapshot[Tariff.Code.BASE].access_duration_days == 90
    assert tariff_snapshot[Tariff.Code.MENTOR].title == "С ментором"
    assert tariff_snapshot[Tariff.Code.MENTOR].price_amount == Decimal("80000.00")
    assert tariff_snapshot[Tariff.Code.MENTOR].access_duration_days == 180
    assert tariff_snapshot[Tariff.Code.VIP].title == "VIP"
    assert tariff_snapshot[Tariff.Code.VIP].price_amount == Decimal("120000.00")
    assert tariff_snapshot[Tariff.Code.VIP].access_duration_days is None
    assert set(
        TariffEntitlement.objects.filter(
            tariff__code=Tariff.Code.WORKSHOP,
            entitlement_type=TariffEntitlement.EntitlementType.MODULE,
        ).values_list("module__slug", flat=True)
    ) == {"start", "workshop"}
    assert set(
        TariffEntitlement.objects.filter(tariff__code=Tariff.Code.BASE).values_list(
            "module__slug",
            flat=True,
        )
    ) == {
        "start",
        "personal-brand-foundation",
        "platform-safe-launch",
        "content-factory",
        "monetization-funnels",
    }
    assert not TariffEntitlement.objects.filter(
        tariff__code=Tariff.Code.BASE,
        code="course-full",
    ).exists()


@pytest.mark.django_db
def test_ensure_stage3_preview_course_is_idempotent_and_updates_existing_seed_nodes() -> None:
    course = Course.objects.create(
        slug=STAGE3_PREVIEW_COURSE_SLUG,
        title="Outdated Course",
        summary="old summary",
        publication_status=Course.PublicationStatus.DRAFT,
        position=9,
        estimated_duration_minutes=0,
    )
    module = Module.objects.create(
        course=course,
        slug="start",
        title="Old Start",
        summary="old summary",
        publication_status=Module.PublicationStatus.DRAFT,
        position=9,
    )
    Lesson.objects.create(
        module=module,
        slug="lesson-0",
        title="Old Lesson 0",
        summary="old summary",
        publication_status=Lesson.PublicationStatus.DRAFT,
        position=9,
        estimated_duration_minutes=0,
    )
    Lesson.objects.create(
        module=module,
        slug="old-start-lesson",
        title="Old extra lesson",
        summary="old summary",
        publication_status=Lesson.PublicationStatus.DRAFT,
        position=10,
        estimated_duration_minutes=0,
    )
    legacy_module = Module.objects.create(
        course=course,
        slug="sales-foundation",
        title="Legacy sales foundation",
        summary="legacy summary",
        publication_status=Module.PublicationStatus.DRAFT,
        position=10,
    )
    Lesson.objects.create(
        module=legacy_module,
        slug="legacy-sales-foundation-lesson",
        title="Legacy lesson",
        summary="legacy summary",
        publication_status=Lesson.PublicationStatus.DRAFT,
        position=0,
        estimated_duration_minutes=0,
    )
    stale_tariff = Tariff.objects.create(
        code=Tariff.Code.BASE,
        course=course,
        title="Old Base",
        price_amount=Decimal("39990.00"),
    )
    TariffEntitlement.objects.create(
        tariff=stale_tariff,
        code="course-full",
        title="Old full course",
        entitlement_type=TariffEntitlement.EntitlementType.COURSE,
        course=course,
    )

    first_course = ensure_stage3_preview_course()
    second_course = ensure_stage3_preview_course()

    updated_course = Course.objects.get(slug=STAGE3_PREVIEW_COURSE_SLUG)
    updated_module = Module.objects.get(course=updated_course, slug="start")
    updated_lesson = Lesson.objects.get(module=updated_module, slug="lesson-0")

    assert first_course.id == second_course.id == updated_course.id
    assert updated_course.title == "Курс Гатса: продажи"
    assert updated_course.publication_status == Course.PublicationStatus.PUBLISHED
    assert updated_course.position == 0
    assert updated_module.title == "Старт"
    assert updated_module.publication_status == Module.PublicationStatus.PUBLISHED
    assert updated_module.position == 0
    assert updated_lesson.title == "Урок 0. Вход после диагностики"
    assert updated_lesson.publication_status == Lesson.PublicationStatus.PUBLISHED
    assert updated_lesson.position == 0
    assert Course.objects.count() == 1
    assert Module.objects.count() == 9
    assert Lesson.objects.count() == 83
    assert not updated_module.lessons.filter(slug="old-start-lesson").exists()
    assert not updated_course.modules.filter(slug="sales-foundation").exists()
    stale_tariff.refresh_from_db()
    assert stale_tariff.title == "Базовый"
    assert stale_tariff.price_amount == Decimal("50000.00")
    assert not stale_tariff.entitlements.filter(code="course-full").exists()


@pytest.mark.django_db
def test_management_command_ensures_stage3_preview_course() -> None:
    stdout = StringIO()

    call_command("ensure_stage3_preview_course", stdout=stdout)

    assert Course.objects.filter(
        slug=STAGE3_PREVIEW_COURSE_SLUG,
        publication_status=Course.PublicationStatus.PUBLISHED,
    ).exists()
    assert "Ensured Stage 3 preview course 'gatsa-sales' with 9 modules and 83 lessons." in (
        stdout.getvalue()
    )
