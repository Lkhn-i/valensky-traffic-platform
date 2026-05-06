from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class DiagnosticHandoff(models.Model):
    class Source(models.TextChoices):
        DIAGNOSTIC_SITE = "diagnostic_site", "Сайт диагностики"
        TELEGRAM_BOT = "telegram_bot", "Telegram-бот"
        MANUAL = "manual", "Вручную"

    class Status(models.TextChoices):
        CREATED = "created", "Создан"
        RESOLVED = "resolved", "Обработан"
        EXPIRED = "expired", "Истёк"
        REVOKED = "revoked", "Отозван"

    source = models.CharField(
        "источник",
        max_length=32,
        choices=Source.choices,
        default=Source.DIAGNOSTIC_SITE,
    )
    external_session_id = models.CharField("внешняя сессия", max_length=128)
    idempotency_key = models.CharField("ключ идемпотентности", max_length=160, unique=True)
    token_hash = models.CharField("хэш токена", max_length=128, unique=True)
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.CREATED,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diagnostic_handoffs",
    )
    lead_profile = models.ForeignKey(
        "accounts.LeadProfile",
        verbose_name="профиль лида",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diagnostic_handoffs",
    )
    diagnostic_segment = models.CharField("сегмент диагностики", max_length=128, blank=True)
    raw_payload = models.JSONField("сырые данные", default=dict, blank=True)
    submitted_at = models.DateTimeField("получено", default=timezone.now)
    expires_at = models.DateTimeField("истекает")
    resolved_at = models.DateTimeField("обработано", null=True, blank=True)
    replay_count = models.PositiveIntegerField("повторные открытия", default=0)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        verbose_name = "передача из диагностики"
        verbose_name_plural = "передачи из диагностики"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_session_id"],
                name="diagnostic_handoff_source_session_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "expires_at"], name="diag_handoff_status_exp_idx"),
            models.Index(fields=["lead_profile", "status"], name="diag_handoff_lead_status_idx"),
        ]

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    def __str__(self) -> str:
        return f"Передача {self.external_session_id}: {self.get_status_display()}"
