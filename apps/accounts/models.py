from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Project user contract. Domain-specific roles live in Role/UserRole."""

    display_name = models.CharField("имя на платформе", max_length=255, blank=True)
    phone = models.CharField("телефон", max_length=32, blank=True)
    timezone = models.CharField("часовой пояс", max_length=64, default="Europe/Moscow")
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"

    def __str__(self) -> str:
        return self.display_name or self.get_username()


class Role(models.Model):
    class Code(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Супер админ"
        ADMIN = "admin", "Админ"
        MANAGER = "manager", "Менеджер"
        STUDENT = "student", "Ученик"
        LEAD = "lead", "Лид"
        SYSTEM = "system", "Система"

    code = models.CharField("код", max_length=32, choices=Code.choices, unique=True)
    title = models.CharField("название", max_length=120)
    description = models.TextField("описание", blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "роль"
        verbose_name_plural = "роли"

    def __str__(self) -> str:
        return self.title


class UserRole(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        related_name="role_links",
    )
    role = models.ForeignKey(
        Role,
        verbose_name="роль",
        on_delete=models.PROTECT,
        related_name="user_links",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="кто выдал",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_role_links",
    )
    reason = models.TextField("причина", blank=True)
    granted_at = models.DateTimeField("выдано", default=timezone.now)

    class Meta:
        ordering = ["user_id", "role__code"]
        verbose_name = "роль пользователя"
        verbose_name_plural = "роли пользователей"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="accounts_unique_user_role")
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.role.code}"


class UserTelegramIdentity(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        related_name="telegram_identities",
    )
    telegram_id = models.BigIntegerField("Telegram ID", unique=True)
    username = models.CharField("логин Telegram", max_length=255, blank=True)
    first_name = models.CharField("имя", max_length=255, blank=True)
    last_name = models.CharField("фамилия", max_length=255, blank=True)
    linked_at = models.DateTimeField("привязано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        ordering = ["telegram_id"]
        verbose_name = "Telegram-профиль"
        verbose_name_plural = "Telegram-профили"

    def __str__(self) -> str:
        return self.username or str(self.telegram_id)


class LeadProfile(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        PREVIEW = "preview", "Пробный доступ"
        REGISTERED = "registered", "Зарегистрирован"
        CONVERTED = "converted", "Оплатил"
        ARCHIVED = "archived", "В архиве"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        related_name="lead_profile",
    )
    status = models.CharField("статус", max_length=32, choices=Status.choices, default=Status.NEW)
    source = models.CharField("источник", max_length=64, default="diagnostic")
    diagnostic_session_id = models.CharField("сессия диагностики", max_length=128, blank=True)
    diagnostic_segment = models.CharField("сегмент диагностики", max_length=128, blank=True)
    consent_snapshot = models.JSONField("согласия", default=dict, blank=True)
    metadata = models.JSONField("метаданные", default=dict, blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "профиль лида"
        verbose_name_plural = "профили лидов"
        indexes = [
            models.Index(fields=["status"], name="accounts_lead_status_idx"),
            models.Index(fields=["diagnostic_session_id"], name="accounts_lead_diag_idx"),
        ]

    def __str__(self) -> str:
        return f"Лид {self.user_id}: {self.get_status_display()}"


class MagicLink(models.Model):
    class Purpose(models.TextChoices):
        LOGIN = "login", "Вход"
        DIAGNOSTIC_PREVIEW = "diagnostic_preview", "Пробный вход из диагностики"
        PAYMENT_ACCESS = "payment_access", "Платный доступ"
        ADMIN_INVITE = "admin_invite", "Приглашение администратора"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="magic_links",
    )
    purpose = models.CharField("назначение", max_length=32, choices=Purpose.choices)
    token_hash = models.CharField("хэш токена", max_length=128, unique=True)
    redirect_path = models.CharField("путь после входа", max_length=255, blank=True)
    expires_at = models.DateTimeField("истекает")
    consumed_at = models.DateTimeField("использовано", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="кто создал",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_magic_links",
    )
    metadata = models.JSONField("метаданные", default=dict, blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "магическая ссылка"
        verbose_name_plural = "магические ссылки"
        indexes = [
            models.Index(fields=["purpose", "expires_at"], name="accounts_magic_purpose_exp_idx"),
        ]

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def __str__(self) -> str:
        return f"Ссылка доступа {self.id}: {self.get_purpose_display()}"
