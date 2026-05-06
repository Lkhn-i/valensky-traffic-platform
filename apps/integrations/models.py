from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class ExternalEvent(models.Model):
    class Source(models.TextChoices):
        DIAGNOSTIC_SITE = "diagnostic_site", "Сайт диагностики"
        TELEGRAM_BOT = "telegram_bot", "Telegram-бот"
        PAYMENT_PROVIDER = "payment_provider", "Платёжный провайдер"
        VIDEO_HOSTING = "video_hosting", "Видеохостинг"
        MANUAL = "manual", "Вручную"

    class ProcessingStatus(models.TextChoices):
        RECEIVED = "received", "Получено"
        PROCESSED = "processed", "Обработано"
        FAILED = "failed", "Ошибка"
        IGNORED = "ignored", "Проигнорировано"

    source = models.CharField("источник", max_length=32, choices=Source.choices)
    event_type = models.CharField("тип события", max_length=100)
    idempotency_key = models.CharField("ключ идемпотентности", max_length=180, unique=True)
    processing_status = models.CharField(
        "статус обработки",
        max_length=16,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.RECEIVED,
    )
    payload = models.JSONField("данные", default=dict, blank=True)
    received_at = models.DateTimeField("получено", default=timezone.now)
    processed_at = models.DateTimeField("обработано", null=True, blank=True)
    error = models.TextField("ошибка", blank=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        verbose_name = "входящее событие интеграции"
        verbose_name_plural = "входящие события интеграций"
        indexes = [
            models.Index(fields=["source", "event_type"], name="integr_event_source_type_idx"),
            models.Index(
                fields=["processing_status", "received_at"],
                name="integr_event_status_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Входящее событие {self.event_type}: {self.get_processing_status_display()}"


class IntegrationOutboxEvent(models.Model):
    class Destination(models.TextChoices):
        TELEGRAM_BOT = "telegram_bot", "Telegram-бот"

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "Ожидает отправки"
        SENT = "sent", "Отправлено"
        FAILED = "failed", "Ошибка"
        DEAD_LETTER = "dead_letter", "Не доставлено"
        CANCELED = "canceled", "Отменено"

    destination = models.CharField("получатель", max_length=32, choices=Destination.choices)
    event_type = models.CharField("тип события", max_length=100)
    idempotency_key = models.CharField("ключ идемпотентности", max_length=180, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="integration_outbox_events",
    )
    notification_job = models.ForeignKey(
        "notifications.NotificationJob",
        verbose_name="уведомление",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="integration_outbox_events",
    )
    processing_status = models.CharField(
        "статус обработки",
        max_length=16,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    payload = models.JSONField("данные", default=dict, blank=True)
    scheduled_at = models.DateTimeField("запланировано", default=timezone.now)
    sent_at = models.DateTimeField("отправлено", null=True, blank=True)
    attempts = models.PositiveSmallIntegerField("попытки", default=0)
    last_error = models.TextField("последняя ошибка", blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        ordering = ["scheduled_at", "id"]
        verbose_name = "исходящее событие интеграции"
        verbose_name_plural = "исходящие события интеграций"
        indexes = [
            models.Index(
                fields=["destination", "event_type"],
                name="integr_outbox_dest_type_idx",
            ),
            models.Index(
                fields=["processing_status", "scheduled_at"],
                name="integr_outbox_status_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Исходящее событие {self.event_type}: {self.get_processing_status_display()}"
