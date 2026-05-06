from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        abstract = True


class Tariff(TimeStampedModel):
    class Code(models.TextChoices):
        WORKSHOP = "workshop", "Воркшоп"
        BASE = "base", "Базовый"
        MENTOR = "mentor", "С ментором"
        VIP = "vip", "VIP"

    code = models.CharField("код", max_length=32, choices=Code.choices, unique=True)
    course = models.ForeignKey(
        "curriculum.Course",
        verbose_name="курс",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tariffs",
    )
    title = models.CharField("название", max_length=160)
    description = models.TextField("описание", blank=True)
    price_amount = models.DecimalField(
        "цена",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField("валюта", max_length=3, default="RUB")
    access_duration_days = models.PositiveIntegerField(
        "срок доступа в днях",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField("активен", default=True)
    sort_order = models.PositiveIntegerField("сортировка", default=0)
    metadata = models.JSONField("метаданные", default=dict, blank=True)

    class Meta:
        ordering = ["sort_order", "price_amount", "id"]
        verbose_name = "тариф"
        verbose_name_plural = "тарифы"
        indexes = [
            models.Index(fields=["is_active", "sort_order"], name="access_tariff_active_sort_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class TariffEntitlement(TimeStampedModel):
    class EntitlementType(models.TextChoices):
        COURSE = "course", "Курс"
        MODULE = "module", "Модуль"
        LESSON = "lesson", "Урок"
        RESOURCE = "resource", "Материал"
        HOMEWORK_REVIEW = "homework_review", "Проверка домашних заданий"
        BONUS = "bonus", "Бонус"
        COMMUNITY = "community", "Сообщество"
        VIP_SUPPORT = "vip_support", "VIP поддержка"

    tariff = models.ForeignKey(
        Tariff,
        verbose_name="тариф",
        on_delete=models.CASCADE,
        related_name="entitlements",
    )
    code = models.CharField("код", max_length=64)
    title = models.CharField("название", max_length=160)
    entitlement_type = models.CharField(
        "тип права",
        max_length=32,
        choices=EntitlementType.choices,
    )
    course = models.ForeignKey(
        "curriculum.Course",
        verbose_name="курс",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tariff_entitlements",
    )
    module = models.ForeignKey(
        "curriculum.Module",
        verbose_name="модуль",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tariff_entitlements",
    )
    lesson = models.ForeignKey(
        "curriculum.Lesson",
        verbose_name="урок",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tariff_entitlements",
    )
    resource = models.ForeignKey(
        "resources.Resource",
        verbose_name="материал",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tariff_entitlements",
    )
    reference_key = models.CharField("ключ привязки", max_length=160, blank=True)
    config = models.JSONField("настройки", default=dict, blank=True)

    class Meta:
        ordering = ["tariff_id", "code"]
        verbose_name = "право тарифа"
        verbose_name_plural = "права тарифов"
        constraints = [
            models.UniqueConstraint(
                fields=["tariff", "code"],
                name="access_tariff_entitlement_code_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["entitlement_type", "reference_key"],
                name="ac_ent_type_ref_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tariff.title}: {self.title}"


class BonusAccess(TimeStampedModel):
    tariff = models.ForeignKey(
        Tariff,
        verbose_name="тариф",
        on_delete=models.CASCADE,
        related_name="bonus_accesses",
    )
    code = models.CharField("код", max_length=64)
    title = models.CharField("название", max_length=160)
    description = models.TextField("описание", blank=True)
    resource = models.ForeignKey(
        "resources.Resource",
        verbose_name="материал",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bonus_accesses",
    )
    starts_after_purchase_minutes = models.PositiveIntegerField(
        "старт после покупки, минут",
        default=0,
    )
    availability_window_hours = models.PositiveIntegerField("окно доступности, часов", default=48)
    config = models.JSONField("настройки", default=dict, blank=True)

    class Meta:
        ordering = ["tariff_id", "code"]
        verbose_name = "бонусный доступ"
        verbose_name_plural = "бонусные доступы"
        constraints = [
            models.UniqueConstraint(fields=["tariff", "code"], name="access_bonus_code_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.tariff.title}: {self.title}"


class Enrollment(TimeStampedModel):
    class Source(models.TextChoices):
        PREVIEW = "preview", "Пробный доступ"
        PAYMENT = "payment", "Оплата"
        MANUAL = "manual", "Вручную"
        IMPORT = "import", "Импорт"

    class Status(models.TextChoices):
        PREVIEW = "preview", "Пробный доступ"
        ACTIVE = "active", "Активен"
        COMPLETED = "completed", "Завершён"
        CANCELED = "canceled", "Отменён"
        ARCHIVED = "archived", "В архиве"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    course = models.ForeignKey(
        "curriculum.Course",
        verbose_name="курс",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    tariff = models.ForeignKey(
        Tariff,
        verbose_name="тариф",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments",
    )
    source = models.CharField(
        "источник",
        max_length=16,
        choices=Source.choices,
        default=Source.PREVIEW,
    )
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.PREVIEW,
    )
    started_at = models.DateTimeField("начато", default=timezone.now)
    completed_at = models.DateTimeField("завершено", null=True, blank=True)
    metadata = models.JSONField("метаданные", default=dict, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        verbose_name = "зачисление"
        verbose_name_plural = "зачисления"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"],
                name="access_enrollment_user_course_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["course", "status"], name="ac_enroll_course_stat_idx"),
        ]

    def __str__(self) -> str:
        return f"Зачисление {self.user_id}: {self.get_status_display()}"


class PreviewAccessGrant(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        CONSUMED = "consumed", "Использован"
        EXPIRED = "expired", "Истёк"
        REVOKED = "revoked", "Отозван"

    lead_profile = models.ForeignKey(
        "accounts.LeadProfile",
        verbose_name="профиль лида",
        on_delete=models.CASCADE,
        related_name="preview_grants",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        related_name="preview_grants",
    )
    course = models.ForeignKey(
        "curriculum.Course",
        verbose_name="курс",
        on_delete=models.CASCADE,
        related_name="preview_grants",
    )
    lesson = models.ForeignKey(
        "curriculum.Lesson",
        verbose_name="урок",
        on_delete=models.CASCADE,
        related_name="preview_grants",
    )
    diagnostic_handoff = models.ForeignKey(
        "diagnostic_handoff.DiagnosticHandoff",
        verbose_name="передача из диагностики",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preview_grants",
    )
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    starts_at = models.DateTimeField("начинается", default=timezone.now)
    expires_at = models.DateTimeField("истекает")
    consumed_at = models.DateTimeField("использовано", null=True, blank=True)
    revoked_at = models.DateTimeField("отозвано", null=True, blank=True)
    reason = models.TextField("причина", blank=True)

    class Meta:
        ordering = ["-starts_at", "-id"]
        verbose_name = "пробный доступ"
        verbose_name_plural = "пробные доступы"
        constraints = [
            models.UniqueConstraint(
                fields=["lead_profile", "lesson"],
                name="access_preview_lead_lesson_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "status", "expires_at"],
                name="access_preview_user_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Пробный доступ {self.user_id}: {self.get_status_display()}"


class AccessGrant(TimeStampedModel):
    class Source(models.TextChoices):
        PAYMENT = "payment", "Оплата"
        MANUAL = "manual", "Вручную"
        IMPORT = "import", "Импорт"
        UPGRADE = "upgrade", "Апгрейд"

    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        REVOKED = "revoked", "Отозван"
        EXPIRED = "expired", "Истёк"
        FROZEN = "frozen", "Заморожен"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    course = models.ForeignKey(
        "curriculum.Course",
        verbose_name="курс",
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    tariff = models.ForeignKey(
        Tariff,
        verbose_name="тариф",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_grants",
    )
    source = models.CharField(
        "источник",
        max_length=16,
        choices=Source.choices,
        default=Source.MANUAL,
    )
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    starts_at = models.DateTimeField("начинается", default=timezone.now)
    expires_at = models.DateTimeField("истекает", null=True, blank=True)
    revoked_at = models.DateTimeField("отозвано", null=True, blank=True)
    source_reference = models.CharField("ссылка на источник", max_length=160, blank=True)
    reason = models.TextField("причина", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="кто выдал",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_access_grants",
    )
    metadata = models.JSONField("метаданные", default=dict, blank=True)

    class Meta:
        ordering = ["-starts_at", "-id"]
        verbose_name = "доступ к обучению"
        verbose_name_plural = "доступы к обучению"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_reference"],
                condition=~Q(source_reference=""),
                name="access_grant_source_ref_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "course", "status"], name="ac_grant_user_course_stat_idx"),
            models.Index(fields=["source", "source_reference"], name="access_grant_source_ref_idx"),
        ]

    def __str__(self) -> str:
        return f"Доступ {self.user_id}: {self.get_status_display()}"
