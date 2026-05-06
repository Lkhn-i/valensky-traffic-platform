from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class NotificationJob(models.Model):
    class Channel(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        EMAIL = "email", "Почта"
        SYSTEM = "system", "Система"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает отправки"
        SENT = "sent", "Отправлено"
        FAILED = "failed", "Ошибка"
        DEAD_LETTER = "dead_letter", "Не доставлено"
        CANCELED = "canceled", "Отменено"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_jobs",
    )
    channel = models.CharField("канал", max_length=16, choices=Channel.choices)
    template_key = models.CharField("ключ шаблона", max_length=100)
    dedupe_key = models.CharField("ключ идемпотентности", max_length=180, null=True, blank=True)
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
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
        verbose_name = "уведомление"
        verbose_name_plural = "уведомления"
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=Q(dedupe_key__isnull=False),
                name="notify_job_dedupe_key_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="notify_job_status_schedule_idx"),
            models.Index(fields=["channel", "template_key"], name="notify_job_channel_tpl_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.channel}:{self.template_key}:{self.status}"
