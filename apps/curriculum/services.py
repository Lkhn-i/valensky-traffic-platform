from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from django.db import transaction
from django.db.models import QuerySet

from apps.access_control.models import Tariff, TariffEntitlement
from apps.resources.models import Resource

from .models import Course, Lesson, LessonBlock, Module


class CurriculumCatalogService(Protocol):
    def list_courses(self, *, publication_status: str | None = None) -> QuerySet[Course]:
        ...

    def get_course(self, *, slug: str) -> Course:
        ...

    def list_lessons(self, *, course_slug: str) -> QuerySet[Lesson]:
        ...


class ORMCurriculumCatalogService:
    def list_courses(self, *, publication_status: str | None = None) -> QuerySet[Course]:
        queryset = Course.objects.prefetch_related("modules__lessons__blocks")
        if publication_status:
            queryset = queryset.filter(publication_status=publication_status)
        return queryset.order_by(*Course._meta.ordering)

    def get_course(self, *, slug: str) -> Course:
        return self.list_courses().get(slug=slug)

    def list_lessons(self, *, course_slug: str) -> QuerySet[Lesson]:
        return (
            Lesson.objects.filter(module__course__slug=course_slug)
            .select_related("module", "module__course")
            .order_by(*Lesson._meta.ordering)
        )


class StubCurriculumCatalogService:
    def list_courses(self, *, publication_status: str | None = None) -> QuerySet[Course]:
        return Course.objects.none()

    def get_course(self, *, slug: str) -> Course:
        raise Course.DoesNotExist(f"Course with slug={slug!r} is not available in the stub")

    def list_lessons(self, *, course_slug: str) -> QuerySet[Lesson]:
        return Lesson.objects.none()


@dataclass(frozen=True)
class Stage3LessonSeed:
    slug: str
    title: str
    position: int
    summary: str
    estimated_duration_minutes: int


@dataclass(frozen=True)
class Stage3ModuleSeed:
    slug: str
    title: str
    position: int
    summary: str
    lessons: tuple[Stage3LessonSeed, ...]


@dataclass(frozen=True)
class Stage3CourseSeed:
    slug: str
    title: str
    summary: str
    description: str
    estimated_duration_minutes: int
    modules: tuple[Stage3ModuleSeed, ...]


@dataclass(frozen=True)
class Stage5BlockSeed:
    position: int
    block_type: str
    title: str
    body: str
    payload: dict[str, object]


@dataclass(frozen=True)
class Stage3TariffSeed:
    code: str
    title: str
    description: str
    price_amount: Decimal
    sort_order: int
    access_duration_days: int | None
    module_slugs: tuple[str, ...] = ()
    includes_full_course: bool = False
    extra_entitlements: tuple[tuple[str, str, str], ...] = ()


STAGE3_PREVIEW_COURSE_SLUG = "gatsa-sales"


def _stage3_lesson_seed(
    *,
    lesson_number: int,
    title: str,
    position: int,
    estimated_duration_minutes: int,
) -> Stage3LessonSeed:
    return Stage3LessonSeed(
        slug=f"lesson-{lesson_number}",
        title=f"Урок {lesson_number}. {title}",
        position=position,
        summary=title,
        estimated_duration_minutes=estimated_duration_minutes,
    )


def _stage3_module_seed(
    *,
    slug: str,
    title: str,
    position: int,
    summary: str,
    lesson_titles: tuple[str, ...],
    first_lesson_number: int,
    lesson_duration_minutes: int = 20,
) -> Stage3ModuleSeed:
    lessons = tuple(
        _stage3_lesson_seed(
            lesson_number=first_lesson_number + lesson_position,
            title=lesson_title,
            position=lesson_position,
            estimated_duration_minutes=lesson_duration_minutes,
        )
        for lesson_position, lesson_title in enumerate(lesson_titles)
    )
    return Stage3ModuleSeed(
        slug=slug,
        title=title,
        position=position,
        summary=summary,
        lessons=lessons,
    )


STAGE3_PREVIEW_MODULES: tuple[Stage3ModuleSeed, ...] = (
    Stage3ModuleSeed(
        slug="start",
        title="Старт",
        position=0,
        summary="Вводный блок после диагностики с открытым Уроком 0.",
        lessons=(
            Stage3LessonSeed(
                slug="lesson-0",
                title="Урок 0. Вход после диагностики",
                position=0,
                summary="Открытый урок для лида, который пришёл после диагностики.",
                estimated_duration_minutes=15,
            ),
        ),
    ),
    _stage3_module_seed(
        slug="workshop",
        title="Воркшоп 1500: быстрый входной продукт / tripwire",
        position=1,
        summary="Отдельная ветка для быстрой микропобеды и апселла в основную программу.",
        lesson_titles=(
            "Быстрый выбор ниши, боли и обещания",
            "Формула сильного короткого ролика",
            "5 сценариев Reels/Shorts и шаблон Telegram-поста",
            "Простая схема контент -> Telegram -> следующий шаг",
            "Что делать дальше, чтобы превратить единичный результат в систему",
        ),
        first_lesson_number=1,
        lesson_duration_minutes=15,
    ),
    _stage3_module_seed(
        slug="personal-brand-foundation",
        title="Модуль 1. Фундамент личного бренда",
        position=2,
        summary="Позиционирование, ядро аудитории и контентный угол без хаоса.",
        lesson_titles=(
            "Рынок, спрос и карты внимания 2026",
            'Модель "кто я для аудитории"',
            "Ядро целевой аудитории",
            '"Я-ниша" и личный угол',
            "Темы, за которыми следят и которые ищут",
            "Причина подписки",
            "Упаковка профиля и первого впечатления",
            "Контентная стратегия на 30 дней",
        ),
        first_lesson_number=6,
    ),
    _stage3_module_seed(
        slug="platform-safe-launch",
        title="Модуль 2. Platform-safe техничка, алгоритмы и первые публикации",
        position=3,
        summary="Безопасный запуск публикаций, первые форматы и первые данные по охватам.",
        lesson_titles=(
            "Platform-safe старт",
            "Как устроено распределение охватов в коротком контенте",
            "Оригинальность против low-value reposts",
            "AI-disclosure, copyright, музыка и Content ID",
            "Формула сильного короткого видео",
            "Форматная логика 2026",
            "Native packaging под каждую платформу",
            "Первые 10-20 публикаций",
            "Видео-подложки, talking-head, скринкасты и UGC-кадры",
            "Telegram как следующий шаг",
            "Разбор первых метрик",
        ),
        first_lesson_number=14,
    ),
    _stage3_module_seed(
        slug="content-factory",
        title="Модуль 3. Фабрика контента",
        position=4,
        summary="AI-production, social search, UGC и управляемая контент-операционка.",
        lesson_titles=(
            "AI как контент-операционка",
            "AI-production pipeline",
            "Личный GPT/AI-раздел",
            "Anti-AI-slop и human proof",
            "Comment mining и разведка спроса",
            "Social search / SEO / AEO для контента",
            "FAQ и evergreen ролики",
            "Банк вирусных идей и scoring-чеклист",
            "Reels/Shorts/TikTok-поток",
            "Карусели, текстовые посты и Telegram-repurposing",
            "UGC и faceless-решения",
            "Creative testing lab",
            "Аналитика контента",
            "Контент-календарь и недельный продакшн-ритм",
        ),
        first_lesson_number=25,
    ),
    _stage3_module_seed(
        slug="monetization-funnels",
        title="Модуль 4. Воронки, услуги и монетизация",
        position=5,
        summary="Переход из внимания в Telegram, первые услуги, оффер и воронка.",
        lesson_titles=(
            "Модель монетизации экспертного блога",
            "Быстрая монетизация новичка на услугах",
            "Линейка стартовых услуг и первые чеки",
            "Как упаковать услугу в понятный оффер",
            "Telegram как продуктовая среда",
            "Лид-магнит без воды",
            "Мини-продукт как tripwire и фильтр качества аудитории",
            "Сильный оффер",
            "Telegram Ads",
            "Stars, paid subscriptions, платный контент и партнерские посевы",
            "Mini Apps/боты",
            "Контент в Telegram, который ведет к продаже",
            "Декомпозиция воронки",
            "Ключевые метрики",
            "Как не усложнить воронку на старте и не утонуть в сервисах",
        ),
        first_lesson_number=39,
    ),
    _stage3_module_seed(
        slug="paid-organic-growth",
        title="Модуль 5. Paid + Organic Growth System",
        position=6,
        summary="Связка органики, ретаргетинга и платной дистрибуции в growth-систему.",
        lesson_titles=(
            "Paid basics",
            "Tracking stack",
            "Telegram Ads: посевы и закупка внимания",
            "TikTok Smart+ и Symphony",
            "Spark Ads и creator-led amplification",
            "Meta Advantage+, Reels ads и partnership ads",
            "YouTube Shorts ads, Demand Gen и Google AI Max for Search",
            "Ретаргетинг и аудитории прогрева",
            "UGC/creator briefs, usage rights и approvals",
            "Бюджетирование и антихаос",
            "Dashboard руководителя",
        ),
        first_lesson_number=54,
    ),
    _stage3_module_seed(
        slug="brand-packaging",
        title="Модуль 6. Продвинутая упаковка бренда",
        position=7,
        summary="Смыслы, визуальная система, прогревы и запуск через Telegram.",
        lesson_titles=(
            "Доупаковка личности",
            "Карта смыслов",
            "Визуальная система бренда",
            "Сторителлинг без графомании",
            "Прогрев к личности, трансформации, методу и продукту",
            "Активный и теневой прогрев",
            "Telegram-запуск",
            "Продающий эфир",
            "Календарь запуска на 7-14 дней",
        ),
        first_lesson_number=65,
    ),
    _stage3_module_seed(
        slug="sales-and-diagnostics",
        title="Модуль 7. Продажи в переписке и диагностиках",
        position=8,
        summary="Системное закрытие теплого спроса в оплату через переписку и диагностику.",
        lesson_titles=(
            "Психология и роль продавца",
            "Цель каждой переписки",
            "Структура переписки",
            "Как не сливать продажу ценой",
            "Возражения по формуле ПАП",
            "Лестница 8 касаний после оффера",
            "Диагностика",
            "Продажа через консультацию и продажа без консультации",
            "Дожим, следующий шаг, фиксация решения и возврат в базу",
        ),
        first_lesson_number=74,
    ),
)

STAGE3_PREVIEW_COURSE = Stage3CourseSeed(
    slug=STAGE3_PREVIEW_COURSE_SLUG,
    title="Курс Гатса: продажи",
    summary="Превью курса с Уроком 0, отдельным воркшопом и полной картой из 7 модулей.",
    description=(
        "После диагностики лид получает открытый Урок 0, видит воркшоп как быстрый вход "
        "и всю карту программы по личному бренду, контенту, Telegram-воронкам и продажам."
    ),
    estimated_duration_minutes=sum(
        lesson.estimated_duration_minutes
        for module in STAGE3_PREVIEW_MODULES
        for lesson in module.lessons
    ),
    modules=STAGE3_PREVIEW_MODULES,
)
STAGE3_TARIFFS: tuple[Stage3TariffSeed, ...] = (
    Stage3TariffSeed(
        code="workshop",
        title="Воркшоп",
        description=(
            "Быстрый входной продукт с результатом за 1-2 дня и маршрутом "
            "к полной программе."
        ),
        price_amount=Decimal("1500.00"),
        sort_order=10,
        access_duration_days=14,
        module_slugs=("start", "workshop"),
    ),
    Stage3TariffSeed(
        code="base",
        title="Базовый",
        description=(
            "Модули 1-4, материалы на 3 месяца, шаблоны, таблицы и "
            "самостоятельное прохождение."
        ),
        price_amount=Decimal("50000.00"),
        sort_order=20,
        access_duration_days=90,
        module_slugs=(
            "start",
            "personal-brand-foundation",
            "platform-safe-launch",
            "content-factory",
            "monetization-funnels",
        ),
    ),
    Stage3TariffSeed(
        code="mentor",
        title="С ментором",
        description=(
            "Полный курс с воркшопом, домашними заданиями, проверками куратором, "
            "чатом и Q&A на 6 месяцев."
        ),
        price_amount=Decimal("80000.00"),
        sort_order=30,
        access_duration_days=180,
        includes_full_course=True,
        extra_entitlements=(
            ("homework-review", "Проверка домашних заданий", "homework_review"),
            ("community", "Командный чат", "community"),
        ),
    ),
    Stage3TariffSeed(
        code="vip",
        title="VIP",
        description=(
            "Всё из полного курса, личный чат, 2 созвона, персональные "
            "разборы и бессрочный доступ."
        ),
        price_amount=Decimal("120000.00"),
        sort_order=40,
        access_duration_days=None,
        includes_full_course=True,
        extra_entitlements=(
            ("homework-review", "Проверка домашних заданий", "homework_review"),
            ("community", "Командный чат", "community"),
            ("vip-support", "VIP поддержка", "vip_support"),
        ),
    ),
)


def _stage3_module_defaults(seed: Stage3ModuleSeed) -> dict[str, int | str]:
    return {
        "title": seed.title,
        "summary": seed.summary,
        "publication_status": "published",
        "position": seed.position,
    }


def _stage3_lesson_defaults(seed: Stage3LessonSeed) -> dict[str, int | str]:
    return {
        "title": seed.title,
        "summary": seed.summary,
        "publication_status": "published",
        "position": seed.position,
        "estimated_duration_minutes": seed.estimated_duration_minutes,
    }


def _ensure_stage5_lesson_blocks(*, lesson: Lesson) -> None:
    block_specs: tuple[Stage5BlockSeed, ...]
    if lesson.module.position == 0 and lesson.position == 0:
        checklist_resource, _created = Resource.objects.update_or_create(
            slug="lesson-0-first-action-checklist",
            defaults={
                "title": "Чек-лист первого действия",
                "description": "Короткий материал к вводному уроку после диагностики.",
                "resource_type": Resource.ResourceType.CHECKLIST,
                "publication_status": Resource.PublicationStatus.PUBLISHED,
                "source_url": "",
                "download_key": "stage5/lesson-0-first-action-checklist.pdf",
            },
        )
        block_specs = (
            Stage5BlockSeed(
                position=0,
                block_type="rich_text",
                title="Стартовый фокус",
                body=(
                    "Стартовый урок помогает разобрать результат диагностики, "
                    "отметить текущий уровень продаж и зафиксировать первый практический шаг."
                ),
                payload={},
            ),
            Stage5BlockSeed(
                position=1,
                block_type="download",
                title="Чек-лист первого действия",
                body="Короткий материал к уроку для самостоятельной работы.",
                payload={
                    "label": "Открыть чек-лист",
                    "resource_slug": checklist_resource.slug,
                },
            ),
            Stage5BlockSeed(
                position=2,
                block_type="action",
                title="Первый результат",
                body="Сформулируйте, какой разговор с клиентом нужно усилить первым.",
                payload={},
            ),
        )
    else:
        block_specs = (
            Stage5BlockSeed(
                position=0,
                block_type="rich_text",
                title="Ключевая задача урока",
                body=lesson.summary,
                payload={},
            ),
        )

    for block_spec in block_specs:
        LessonBlock.objects.update_or_create(
            lesson=lesson,
            position=block_spec.position,
            defaults={
                "block_type": block_spec.block_type,
                "title": block_spec.title,
                "body": block_spec.body,
                "payload": block_spec.payload,
                "is_required": True,
            },
        )


def _tariff_metadata(seed: Stage3TariffSeed) -> dict[str, object]:
    features: tuple[str, ...]
    if seed.code == Tariff.Code.WORKSHOP:
        features = ("Быстрый результат за 1-2 дня", "Старт + воркшоп", "Маршрут к полной программе")
    elif seed.code == Tariff.Code.BASE:
        features = ("Модули 1-4", "Материалы на 3 месяца", "Шаблоны и таблицы")
    elif seed.code == Tariff.Code.MENTOR:
        features = ("Полный курс", "Проверка домашних заданий", "Чат и Q&A")
    else:
        features = ("Личный чат", "2 созвона", "Персональные разборы", "Доступ навсегда")
    return {
        "features": features,
        "checkout_provider": "robokassa",
        "price_source": "course-program-map",
    }


def _ensure_stage3_tariffs(*, course: Course) -> None:
    module_by_slug = {module.slug: module for module in course.modules.all()}
    for seed in STAGE3_TARIFFS:
        expected_entitlement_codes = {
            *(("course-full",) if seed.includes_full_course else ()),
            *(f"module-{module_slug}" for module_slug in seed.module_slugs),
            *(code for code, _title, _entitlement_type in seed.extra_entitlements),
        }
        tariff, _created = Tariff.objects.update_or_create(
            code=seed.code,
            defaults={
                "course": course,
                "title": seed.title,
                "description": seed.description,
                "price_amount": seed.price_amount,
                "currency": "RUB",
                "access_duration_days": seed.access_duration_days,
                "is_active": True,
                "sort_order": seed.sort_order,
                "metadata": _tariff_metadata(seed),
            },
        )
        TariffEntitlement.objects.filter(tariff=tariff).exclude(
            code__in=expected_entitlement_codes
        ).delete()

        if seed.includes_full_course:
            TariffEntitlement.objects.update_or_create(
                tariff=tariff,
                code="course-full",
                defaults={
                    "title": "Полный курс",
                    "entitlement_type": TariffEntitlement.EntitlementType.COURSE,
                    "course": course,
                    "module": None,
                    "lesson": None,
                    "resource": None,
                    "reference_key": "",
                    "config": {},
                },
            )

        for module_slug in seed.module_slugs:
            module = module_by_slug[module_slug]
            TariffEntitlement.objects.update_or_create(
                tariff=tariff,
                code=f"module-{module.slug}",
                defaults={
                    "title": module.title,
                    "entitlement_type": TariffEntitlement.EntitlementType.MODULE,
                    "course": None,
                    "module": module,
                    "lesson": None,
                    "resource": None,
                    "reference_key": "",
                    "config": {},
                },
            )

        for code, title, entitlement_type in seed.extra_entitlements:
            TariffEntitlement.objects.update_or_create(
                tariff=tariff,
                code=code,
                defaults={
                    "title": title,
                    "entitlement_type": entitlement_type,
                    "course": None,
                    "module": None,
                    "lesson": None,
                    "resource": None,
                    "reference_key": code,
                    "config": {},
                },
            )


def _park_module_positions(*, course: Course) -> None:
    modules = list(course.modules.order_by("position", "id"))
    if not modules:
        return

    next_position = max(module.position for module in modules) + 1000
    for offset, module in enumerate(modules):
        Module.objects.filter(id=module.id).update(position=next_position + offset)


def _park_lesson_positions(*, module: Module) -> None:
    lessons = list(module.lessons.order_by("position", "id"))
    if not lessons:
        return

    next_position = max(lesson.position for lesson in lessons) + 1000
    for offset, lesson in enumerate(lessons):
        Lesson.objects.filter(id=lesson.id).update(position=next_position + offset)


def _sync_stage3_lessons(*, module: Module, lesson_seeds: tuple[Stage3LessonSeed, ...]) -> None:
    _park_lesson_positions(module=module)

    expected_lesson_slugs = {lesson_seed.slug for lesson_seed in lesson_seeds}
    for lesson_seed in lesson_seeds:
        lesson, _created = Lesson.objects.update_or_create(
            module=module,
            slug=lesson_seed.slug,
            defaults=_stage3_lesson_defaults(lesson_seed),
        )
        _ensure_stage5_lesson_blocks(lesson=lesson)

    module.lessons.exclude(slug__in=expected_lesson_slugs).delete()


@transaction.atomic
def ensure_stage3_preview_course() -> Course:
    seed = STAGE3_PREVIEW_COURSE
    course, _created = Course.objects.update_or_create(
        slug=seed.slug,
        defaults={
            "title": seed.title,
            "summary": seed.summary,
            "description": seed.description,
            "publication_status": Course.PublicationStatus.PUBLISHED,
            "position": 0,
            "estimated_duration_minutes": seed.estimated_duration_minutes,
        },
    )

    _park_module_positions(course=course)
    expected_module_slugs = {module_seed.slug for module_seed in seed.modules}
    for module_seed in seed.modules:
        module, _created = Module.objects.update_or_create(
            course=course,
            slug=module_seed.slug,
            defaults=_stage3_module_defaults(module_seed),
        )
        _sync_stage3_lessons(module=module, lesson_seeds=module_seed.lessons)

    course.modules.exclude(slug__in=expected_module_slugs).delete()

    _ensure_stage3_tariffs(course=course)
    return ORMCurriculumCatalogService().get_course(slug=course.slug)
